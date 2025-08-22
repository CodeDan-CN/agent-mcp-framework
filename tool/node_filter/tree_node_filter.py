import asyncio
import json
import time
from urllib.parse import urljoin

from mcp.server import FastMCP
from openai import OpenAI

client = OpenAI(api_key="sk-", base_url="https://api.aigc369.com/v1")
PRODUCT_KEYWORDS = "产品 服务 商城 商品 购买 销售 汽车 各类不同行业商品 catalog shop"

mcp = FastMCP()

def fix_urls(nav_nodes, base_url):
    """修复URL"""
    for node in nav_nodes:
        url = "" if node.get("url", "") is None else node.get("url", "")
        url = url.strip()
        if not url or url.lower().startswith("javascript:void"):
            node["url"] = base_url
        elif url.startswith("/"):
            node["url"] = urljoin(base_url, url)
        children = node.get("children", [])
        if children:
            fix_urls(children, base_url)

def flatten_for_scoring(nav_nodes, parent_titles=None, parent_features=None):
    """
    展平为“行”（每行一个 path），返回 list[dict]:
    {
      "text": 送模型用的文本（path + 特征）,
      "path": "A > B > C",
      "url": 最终修复后的 URL,
      "features": [...],
      "node": 节点对象引用（用于回写分数）
    }
    """
    if parent_titles is None:
        parent_titles = []
    if parent_features is None:
        parent_features = []

    flat = []
    for node in nav_nodes:
        current_path = parent_titles + [node.get('title', '')]
        current_features = parent_features + node.get("features", [])
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

        children = node.get("children", [])
        if children:
            flat.extend(flatten_for_scoring(children, current_path, current_features))
    print(f"[flatten_for_scoring] 共展平 {len(flat)} 个节点（行）")
    return flat

def batch_score_relevance(lines):
    """
    让模型给每一行一个 0-100 的相关性分数
    """
    prompt = (
            "你是一个导航结构分析助手，需要判断以下多个路径标题是否与产品和服务内容相关，每个路径都需要打分，"
            f"例如与{PRODUCT_KEYWORDS}等有关。\n\n"
            "- 判定目标：只关注和产品、服务、不同类型可以被称为商品的事物、页数等的导航节点，忽略企业介绍、新闻动态、文化宣传等无关内容。\n"
            "- 分数范围：0~100\n"
            "  - 50以下：完全不相关\n"
            "  - 50-70：可能相关（有潜在关联，但不确定，比如页数调整链接，比如产品类型链接）\n"
            "  - 70以上：确定相关（可以肯定这个路径标题和产品与信息有关）\n"
            "- 输出要求：只输出数字分数，不要解释。\n\n"
            "### 路径列表开始 ###\n" +
            "\n".join(lines) +
            "\n### 路径列表结束 ###"
    )
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        rows = resp.choices[0].message.content.strip().splitlines()
        scores = []
        for r in rows:
            r = r.strip()
            try:
                scores.append(int(r))
            except:
                scores.append(0)
        print(f"[batch_score_relevance] 模型返回 {len(scores)} 个分数")
        return scores
    except Exception as e:
        print("[ERROR] 模型调用异常:", e)
        return [0] * len(lines)

def batch_score_relevance_batched(lines, batch_size=20):
    all_scores = []
    for i in range(0, len(lines), batch_size):
        batch = lines[i:i+batch_size]
        print(f"[batch_score_relevance_batched] 第 {i//batch_size + 1} 批，大小 {len(batch)}")
        sc = batch_score_relevance(batch)
        # 对齐长度（稳妥处理）
        if len(sc) != len(batch):
            print(f"[WARN] 返回数量不匹配：期望 {len(batch)} 实际 {len(sc)}，用0补齐")
            sc = (sc + [0] * len(batch))[:len(batch)]
        all_scores.extend(sc)
        time.sleep(1)
    return all_scores

def normalize_scores(scores):
    """把分数归一化到 0-1 区间"""
    if not scores:
        return []
    mn, mx = min(scores), max(scores)
    if mx == mn:
        return [0.5] * len(scores)
    return [(s - mn) / (mx - mn) for s in scores]

@mcp.tool(name="score_nav_tree")
async def score_nav_tree_tool(tree_json_path: str, level:int):
    """
    基于产品和服务相关性剪枝网站导航树。
    自动分析输入的导航树文件地址，加载其中json数据，判断哪些节点与产品、服务或商业内容相关， 剪除不相关节点，并返回清理后的导航树所在文件地址。

     Args:
         tree_json_path(str): 即导航树json文件地址
         level(int): 当前层级数字

     Returns: dict: 剪枝后的导航树 JSON 文件地址
    """
    with open(tree_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    nav_tree = data.get("nav_tree", [])
    base_url = (data.get("url") or "").strip()
    if base_url:
        print("[main] 修复导航树中的URL...")
        fix_urls(nav_tree, base_url)

    print("[main] 展平为行...")
    flat_rows = flatten_for_scoring(nav_tree)
    lines = [r["text"] for r in flat_rows]

    print("[main] 批量打分（原始分）...")
    scores_raw = batch_score_relevance_batched(lines, batch_size=20)

    print("[main] 归一化分数...")
    scores_norm = normalize_scores(scores_raw)

    print("[main] 绑定分数（逐行 & 回写节点）...")
    flat_scored = []
    for row, raw, norm in zip(flat_rows, scores_raw, scores_norm):
        # 写入“行”结果
        rec = {
            "path": row["path"],
            "url": row["url"],
            "features": row["features"],
            "score_raw": raw,
            "score_norm": round(norm, 4),
        }
        flat_scored.append(rec)

        # 同时把分数写回节点（便于后续基于树做处理）
        row["node"]["score_raw"] = raw
        row["node"]["score_norm"] = round(norm, 4)

    out_path = f"/Users/codedan/local/project/crawlee/agent-mcp-framework/file/data_scored{level}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"[main] 打分完成，已写入 {out_path}")
    return out_path

if __name__ == "__main__":
    # asyncio.run(score_nav_tree_tool("/Users/codedan/local/project/crawlee/agent-mcp-framework/file/data.json"))
    mcp.run(transport='stdio')
