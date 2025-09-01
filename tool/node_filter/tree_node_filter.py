import asyncio
import json
import time
from urllib.parse import urljoin

from mcp.server import FastMCP
from openai import OpenAI

client = OpenAI(api_key="sk-",
                base_url="https://api.aigc369.com/v1")

PRODUCT_KEYWORDS = "产品 服务 商城 商品 购买 销售 汽车 各类不同行业商品 catalog shop"
INTERMEDIATE_KEYWORDS = "类别 分类 系列 品牌 页码 下一页 1 2 3 4 5 6 7 8 9 上一页 下一页 page category list 目录"

mcp = FastMCP()

def fix_urls(nav_nodes, base_url):
    for node in nav_nodes:
        url = node.get("url") or ""
        url = url.strip()
        if not url or url.lower().startswith("javascript:void"):
            node["url"] = base_url
        elif url.startswith("/"):
            node["url"] = urljoin(base_url, url)
        children = node.get("children", [])
        if children:
            fix_urls(children, base_url)

def flatten_leaf_nodes(nav_nodes, parent_titles=None, parent_features=None):
    if parent_titles is None:
        parent_titles = []
    if parent_features is None:
        parent_features = []

    flat = []
    for node in nav_nodes:
        current_path = parent_titles + [node.get('title', '')]
        current_features = parent_features + node.get("features", [])
        children = node.get("children", [])

        if children:
            flat.extend(flatten_leaf_nodes(children, current_path, current_features))
        else:
            path_str = " > ".join(current_path).strip()
            text = path_str
            if current_features:
                text += " | 特征: " + "、".join(map(str, current_features))
            flat.append({
                "text": text,
                "path": path_str,
                "url": node.get("url", ""),
                "features": current_features,
                "node": node,
            })
    print(f"[flatten_leaf_nodes] 共展平 {len(flat)} 个叶子节点")
    return flat

def batch_score_relevance(lines):
    lines_numbered = [f"{i + 1}. {title}" for i, title in enumerate(lines)]
    lines_text = "\n".join(lines_numbered)
    prompt = f"""
下面是评分说明与输入列表。请按语义判断并输出 CSV（编号,产品分,中间页分）：
评分说明（简短）：
- 产品分（Product relevance 0-100）：高分表示该标题直接或非常可能通向商品/服务详情页。
- 中间页分（Intermediate/catalog relevance 0-100）：高分表示该标题更像目录/列表/分类/品牌/分页/聚合页。
- 如果无法判断或输入行为异常，请返回 编号,0,0。
关键词参考：
产品相关：{PRODUCT_KEYWORDS}
中间页相关：{INTERMEDIATE_KEYWORDS}

下面是按编号的输入：
{lines_text}
    """

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "你是一个只返回 CSV 的评分助手，格式：编号,产品分,中间页分，不要输出其它内容。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0
        )
        rows = resp.choices[0].message.content.strip().splitlines()
        scores_product, scores_middle = [], []
        for r in rows:
            parts = r.strip().split(",")
            if len(parts) == 3:
                try:
                    sp, sm = int(parts[1]), int(parts[2])
                except:
                    sp, sm = 0, 0
            else:
                sp, sm = 0, 0
            scores_product.append(sp)
            scores_middle.append(sm)
        print(f"[batch_score_relevance] 模型返回 {len(scores_product)} 个结果")
        return scores_product, scores_middle
    except Exception as e:
        print("[ERROR] 模型调用异常:", e)
        n = len(lines)
        return [0]*n, [0]*n

def batch_score_relevance_batched(lines, batch_size=10):
    all_scores_product, all_scores_middle = [], []
    for i in range(0, len(lines), batch_size):
        batch = lines[i:i+batch_size]
        print(f"[batch_score_relevance_batched] 第 {i//batch_size + 1} 批，大小 {len(batch)}")
        sp, sm = batch_score_relevance(batch)
        if len(sp) != len(batch):
            sp = (sp + [0] * len(batch))[:len(batch)]
            sm = (sm + [0] * len(batch))[:len(batch)]
        all_scores_product.extend(sp)
        all_scores_middle.extend(sm)
        time.sleep(1)
    return all_scores_product, all_scores_middle

def normalize_scores(scores):
    if not scores:
        return []
    mn, mx = min(scores), max(scores)
    if mx == mn:
        return [0.5]*len(scores)
    return [(s - mn)/(mx - mn) for s in scores]

@mcp.tool(name="score_nav_tree")
async def score_nav_tree_tool(tree_json_path: str, level:int):
    """
    基于产品和服务相关性剪枝网站导航树。

    自动分析输入的导航树，判断哪些节点与产品、服务或商业内容相关，
    剪除不相关节点，并返回清理后的导航树。

    Args:
        nav_data (dict): 包含初始导航树的 JSON 对象

    Returns:
        dict: 剪枝后的导航树 JSON 对象，仍保存在 "nav_tree" 字段中。
    """
    with open(tree_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    nav_tree = data.get("nav_tree", [])
    base_url = (data.get("url") or "").strip()
    if base_url:
        print("[main] 修复导航树中的URL...")
        fix_urls(nav_tree, base_url)

    print("[main] 展平为行...")
    flat_rows = flatten_leaf_nodes(nav_tree)
    lines = [r["text"] for r in flat_rows]

    print("[main] 批量打分...")
    scores_product_raw, scores_middle_raw = batch_score_relevance_batched(lines, batch_size=10)
    scores_product_norm = normalize_scores(scores_product_raw)
    scores_middle_norm = normalize_scores(scores_middle_raw)

    print("[main] 计算单一分数并回写节点...")
    for row, sp_raw, sm_raw, sp_norm, sm_norm in zip(flat_rows, scores_product_raw, scores_middle_raw, scores_product_norm, scores_middle_norm):
        # 加权平均，可调权重
        score_norm = round(0.7*sp_norm + 0.3*sm_norm, 4)
        row["node"]["score_raw"] = (sp_raw + sm_raw) / 2
        row["node"]["score_norm"] = score_norm
        row["node"]["crawl_needed"] = score_norm >= 0.7

    out_path = f"/Users/codedan/local/project/crawlee/agent-mcp-framework/file/data_scored{level}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"[main] 打分完成，已写入 {out_path}")
    return out_path

if __name__ == "__main__":
    # asyncio.run(score_nav_tree_tool("../../file/add_tree3.json", level=3))
    mcp.run(transport='stdio')