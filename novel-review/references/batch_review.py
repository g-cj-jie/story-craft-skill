#!/usr/bin/env python3
"""
批量章节评审脚本
用法: python3 batch_review.py --start 51 --end 100
可选: --base-dir /path/to/novel  --output /path/to/report.md
"""

import os
import re
import argparse
from pathlib import Path
from typing import Dict, List, Tuple

# 默认路径（按项目实际结构修改）
DEFAULT_BASE = Path("/mnt/e/AI项目工程/小说/艾泽拉斯：死灵法师之路")

DIMENSIONS = {
    "章纲一致性": 30,
    "三层叙事完整性": 20,
    "世界观一致性": 15,
    "人物一致性": 10,
    "文风一致性": 10,
    "字数达标": 5,
    "伏笔/子剧情": 10,
}


def read_file(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except Exception as e:
        return ""


def parse_outline(content: str) -> Dict:
    o = {"title": "", "chapter_num": 0, "volume": "", "word_count": "",
         "summary": "", "key_scenes": [], "foreshadowing": "", "three_layers": {}}
    section = ""
    for line in content.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("# 第") and "章" in line:
            o["title"] = line[2:].strip()
            m = re.search(r"第(\d+)章", line)
            if m:
                o["chapter_num"] = int(m.group(1))
        elif line.startswith("- 全局章号："):
            o["chapter_num"] = int(line.split("：")[1].strip())
        elif line.startswith("- 所属："):
            o["volume"] = line.split("：")[1].strip()
        elif line.startswith("- 预计字数："):
            o["word_count"] = line.split("：")[1].strip()
        elif line.startswith("## 内容简纲"):
            section = "summary"
        elif line.startswith("## 关键场景"):
            section = "key_scenes"
        elif line.startswith("## 伏笔操作"):
            section = "foreshadowing"
        elif line.startswith("## 三层叙事检查"):
            section = "three_layers"
        elif section == "summary" and not line.startswith("##"):
            o["summary"] += line + "\n"
        elif section == "key_scenes" and re.match(r"^\d+\.", line):
            o["key_scenes"].append(line)
        elif section == "foreshadowing" and not line.startswith("##"):
            o["foreshadowing"] += line + "\n"
        elif section == "three_layers" and line.startswith("- 第"):
            o["three_layers"][line.split("：")[0].strip()] = "✓" in line
    return o


def parse_chapter(content: str) -> Dict:
    c = {"title": "", "content": "", "word_count": 0, "paragraphs": []}
    for line in content.split("\n"):
        if line.startswith("# 第") and "章" in line:
            c["title"] = line[2:].strip()
        elif line.strip():
            c["paragraphs"].append(line.strip())
    c["content"] = "\n".join(c["paragraphs"])
    c["word_count"] = len(c["content"])
    return c


def check_hard_blocks(ch: Dict) -> List[str]:
    blocks = []
    if ch["word_count"] < 3000:
        blocks.append(f"字数严重不足：{ch['word_count']}字（<3000字，需扩充）")
    elif ch["word_count"] > 6000:
        blocks.append(f"字数严重超标：{ch['word_count']}字（>6000字，需拆分或精简）")
    if len(ch["paragraphs"]) < 10:
        blocks.append("章节内容空洞：段落数量过少")
    return blocks


# KEY_SCENES_RULES - 关键场景同义词映射（由LLM评审自动扩充）
KEY_SCENE_SYNONYMS = {
# 格式: "章纲关键词": ["同义词1", "同义词2", ...]
    # 示例: "挥剑": ["劈砍", "用剑攻击", "举剑"],
    "3个关键场景：苏晨在旅店中醒来（'旅店": ["3个关键场景：苏晨在旅店中醒来（'旅店", "3个关键场景：苏晨在旅店中醒来（'旅店变体"],
    "关键场景": ["关键场景", "关键场景变体"],
}

def eval_outline_consistency(ch: Dict, ol: Dict) -> Tuple[int, str]:
    score, notes = 30, []
    missing = []
    for scene in ol["key_scenes"]:
        kw = re.findall(r"[\u4e00-\u9fa5]+", scene)
        found = False
        for k in kw[:3]:
            # 直接匹配
            if k in ch["content"]:
                found = True
                break
            # 同义词匹配
            if k in KEY_SCENE_SYNONYMS:
                if any(syn in ch["content"] for syn in KEY_SCENE_SYNONYMS[k]):
                    found = True
                    break
        if not found:
            missing.append(scene)
    if missing:
        score -= len(missing) * 5
        notes.append(f"缺少{len(missing)}个关键场景（关键词匹配，需人工复核）")
    if ol["foreshadowing"] and "无新增伏笔" not in ol["foreshadowing"]:
        kw = re.findall(r"[\u4e00-\u9fa5]+", ol["foreshadowing"])
        if not any(k in ch["content"] for k in kw[:3]):
            score -= 3
            notes.append("伏笔操作未在正文中体现（关键词匹配，需人工复核）")
    return max(0, score), "; ".join(notes)


def eval_three_layers(ch: Dict, ol: Dict) -> Tuple[int, str]:
    score, notes = 20, []
    last = ch["paragraphs"][-1] if ch["paragraphs"] else ""
    # ENDING_HOOK_RULES - 结尾钩子关键词（由LLM评审自动扩充）
    hooks = ["但是", "然而", "突然", "这时", "就在这时", "没想到", "意外",
             "远处", "背后", "门外", "响起", "传来", "出现", "发现",
             "终于", "开始", "决定", "准备", "即将", "将要"]
    if not any(h in last for h in hooks):
        score -= 5
        notes.append("缺少结尾钩子（基于关键词，隐晦钩子需人工判断）")
    if len(ch["paragraphs"]) < 15:
        score -= 8
        notes.append("疑似纯过渡章")
    return max(0, score), "; ".join(notes)


def eval_world(ch: Dict) -> Tuple[int, str]:
    score, notes = 15, []
    # WORLD_ITEMS_RULES - 现代物品关键词（由LLM评审自动扩充）
    for item in ["手机", "电脑", "汽车", "飞机", "电视", "冰箱", "空调", "互联网"]:
        if item in ch["content"]:
            score -= 5
            notes.append(f"出现现代物品：{item}")
    # OTHER_WORLD_RULES - 其他世界内容关键词（由LLM评审自动扩充）
    for w in ["地球", "中国", "美国", "日本", "欧洲"]:
        if w in ch["content"]:
            score -= 2
            notes.append(f"出现其他世界内容：{w}")
    return max(0, score), "; ".join(notes)


def eval_character(ch: Dict) -> Tuple[int, str]:
    score, notes = 10, []
    if "苏晨" not in ch["content"] and "沈夜" not in ch["content"]:
        score -= 5
        notes.append("主角名字缺失")
    return max(0, score), "; ".join(notes)


def eval_style(ch: Dict) -> Tuple[int, str]:
    score, notes = 10, []
    if re.search(r"##\s*[一二三四五]", ch["content"]):
        score -= 2
        notes.append("出现序号标记分段")
    if ch["word_count"] > 0:
        dash_density = ch["content"].count("——") / (ch["word_count"] / 1000)
        if dash_density > 5:
            score -= 5
            notes.append(f"破折号密度过高：{dash_density:.1f}个/千字")
    paras = ch["paragraphs"]
    for i in range(len(paras) - 2):
        if paras[i][:10] == paras[i + 1][:10] == paras[i + 2][:10]:
            score -= 2
            notes.append("出现重复句式")
            break
    return max(0, score), "; ".join(notes)


def eval_word_count(ch: Dict) -> Tuple[int, str]:
    wc = ch["word_count"]
    if 3000 <= wc <= 6000:
        return 5, f"字数达标：{wc}字"
    return 0, f"字数不达标：{wc}字（需{'扩充' if wc < 3000 else '拆分或精简'}）"


def eval_foreshadowing(ch: Dict, ol: Dict) -> Tuple[int, str]:
    score, notes = 10, []
    if ol["foreshadowing"] and "无新增伏笔" not in ol["foreshadowing"]:
        kw = re.findall(r"[\u4e00-\u9fa5]+", ol["foreshadowing"])
        if not any(k in ch["content"] for k in kw[:3]):
            score -= 3
            notes.append("伏笔操作粗暴或敷衍（需人工复核）")
    return max(0, score), "; ".join(notes)


def evaluate_chapter(num: int, base: Path) -> Dict:
    outline_file = base / "故事大纲" / "章纲" / f"ch-{num}.md"
    chapter_file = base / "章节正文" / f"第{num}章.md"
    if not outline_file.exists():
        return {"error": f"章纲文件不存在：{outline_file}", "chapter": num}
    if not chapter_file.exists():
        return {"error": f"正文文件不存在：{chapter_file}", "chapter": num}
    ol = parse_outline(read_file(outline_file))
    ch = parse_chapter(read_file(chapter_file))
    hb = check_hard_blocks(ch)
    if hb:
        return {"chapter": num, "title": ch["title"], "hard_blocks": hb,
                "total_score": 0, "verdict": "不合格（硬阻断）"}
    evaluators = [
        ("章纲一致性", lambda: eval_outline_consistency(ch, ol)),
        ("三层叙事完整性", lambda: eval_three_layers(ch, ol)),
        ("世界观一致性", lambda: eval_world(ch)),
        ("人物一致性", lambda: eval_character(ch)),
        ("文风一致性", lambda: eval_style(ch)),
        ("字数达标", lambda: eval_word_count(ch)),
        ("伏笔/子剧情", lambda: eval_foreshadowing(ch, ol)),
    ]
    scores, notes = {}, {}
    for name, fn in evaluators:
        scores[name], notes[name] = fn()
    total = sum(scores.values())
    return {"chapter": num, "title": ch["title"], "word_count": ch["word_count"],
            "scores": scores, "notes": notes, "total_score": total,
            "verdict": "通过" if total >= 80 else "需修改"}


def generate_report(results: List[Dict]) -> str:
    r = []
    r.append("# 小说批量评审报告\n")
    r.append(f"**评审时间**：{__import__('datetime').date.today()}\n")
    r.append("---\n")
    total = len(results)
    passed = sum(1 for x in results if x.get("verdict") == "通过")
    r.append("## 一、评审总结\n")
    r.append(f"| 指标 | 数量 |\n|------|------|\n")
    r.append(f"| 评审章节 | {total} |\n| 通过章节 | {passed} |\n")
    r.append(f"| 需修改章节 | {total - passed} |\n| 通过率 | {passed/total*100:.1f}% |\n\n---\n\n")
    r.append("## 二、各章评审结果\n\n")
    r.append("| 章节 | 标题 | 字数 | 总分 | 判定 | 主要问题 |\n")
    r.append("|------|------|------|------|------|----------|\n")
    for res in results:
        if "error" in res:
            r.append(f"| {res.get('chapter','?')} | - | - | - | - | {res['error']} |\n")
            continue
        title = res.get("title", "")[:15]
        issues = res.get("hard_blocks", [])
        if not issues:
            issues = [n for n in res.get("notes", {}).values() if n]
        issue_text = "; ".join(issues)[:60]
        r.append(f"| {res['chapter']} | {title} | {res.get('word_count',0)} | "
                 f"{res.get('total_score',0)} | {res.get('verdict','')} | {issue_text} |\n")
    r.append("\n---\n\n## 三、维度分析\n\n")
    r.append("| 维度 | 平均得分 | 满分 | 得分率 |\n|------|----------|------|--------|\n")
    for dim, mx in DIMENSIONS.items():
        vals = [res["scores"][dim] for res in results if "scores" in res and dim in res["scores"]]
        if vals:
            avg = sum(vals) / len(vals)
            r.append(f"| {dim} | {avg:.1f} | {mx} | {avg/mx*100:.1f}% |\n")
    r.append("\n---\n\n## 四、常见问题汇总\n\n")
    issue_counts = {}
    for res in results:
        for n in res.get("notes", {}).values():
            if n:
                for issue in n.split("; "):
                    issue_counts[issue] = issue_counts.get(issue, 0) + 1
    if issue_counts:
        r.append("| 问题 | 出现次数 |\n|------|----------|\n")
        for issue, cnt in sorted(issue_counts.items(), key=lambda x: -x[1])[:15]:
            r.append(f"| {issue} | {cnt} |\n")
    r.append("\n---\n\n## 五、需修改章节清单\n\n")
    for res in results:
        if res.get("verdict") == "需修改" or "hard_blocks" in res:
            r.append(f"- **第{res['chapter']}章**：{res.get('title','')}\n")
            for hb in res.get("hard_blocks", []):
                r.append(f"  - 🔴 硬阻断：{hb}\n")
            for dim, n in res.get("notes", {}).items():
                if n:
                    r.append(f"  - ⚠️ {dim}：{n}\n")
    return "".join(r)


def main():
    parser = argparse.ArgumentParser(description="批量章节评审")
    parser.add_argument("--start", type=int, required=True, help="起始章节号")
    parser.add_argument("--end", type=int, required=True, help="结束章节号")
    parser.add_argument("--base-dir", type=str, default=str(DEFAULT_BASE))
    parser.add_argument("--output", type=str, default="")
    args = parser.parse_args()
    base = Path(args.base_dir)
    print(f"评审第{args.start}-{args.end}章...")
    results = []
    for n in range(args.start, args.end + 1):
        print(f"  第{n}章...")
        results.append(evaluate_chapter(n, base))
    report = generate_report(results)
    out = Path(args.output) if args.output else base / "评审报告" / f"{__import__('datetime').date.today()}_第{args.start}-{args.end}章评审报告.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    passed = sum(1 for r in results if r.get("verdict") == "通过")
    print(f"完成！通过{passed}/{len(results)}章，报告：{out}")


if __name__ == "__main__":
    main()
