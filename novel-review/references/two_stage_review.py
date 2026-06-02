#!/usr/bin/env python3
"""
两阶段评审脚本
第一阶段：脚本检测（关键词匹配）
第二阶段：LLM复核（语义理解）
第三阶段：自动更新规则（如果LLM判定为误报）

用法:
  python3 two_stage_review.py --start 51 --end 100
  python3 two_stage_review.py --start 51 --end 100 --update-rules
  python3 two_stage_review.py --start 51 --end 100 --report-only
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

# 导入现有脚本
sys.path.insert(0, str(Path(__file__).parent))
from batch_review import evaluate_chapter, generate_report, DEFAULT_BASE
from llm_reviewer import batch_llm_review
from rules_updater import process_llm_results, generate_update_report


def stage1_script_review(start: int, end: int, base: Path) -> tuple:
    """第一阶段：脚本检测
    
    Returns:
        (全部结果, 失败章节列表)
    """
    print(f"🔍 第一阶段：脚本检测（第{start}-{end}章）...")
    
    all_results = []
    failed_chapters = []
    hard_block_chapters = []
    
    for n in range(start, end + 1):
        result = evaluate_chapter(n, base)
        all_results.append(result)
        
        # 收集失败章节
        if result.get("verdict") == "需修改" or "hard_blocks" in result:
            # 硬阻断章节（字数超标/不足）直接标记，不送LLM
            if "hard_blocks" in result:
                hard_block_chapters.append(result)
                continue
            
            issues = result.get("hard_blocks", [])
            if not issues:
                issues = [n for n in result.get("notes", {}).values() if n]
            
            failed_chapters.append({
                "chapter": n,
                "issues": issues,
                "script_verdict": result.get("verdict", "需修改"),
                "scores": result.get("scores", {}),
                "notes": result.get("notes", {})
            })
    
    passed = sum(1 for r in all_results if r.get("verdict") == "通过")
    print(f"  ✅ 脚本检测完成：通过{passed}/{len(all_results)}章")
    print(f"  🔴 硬阻断（字数<3000或>6000，直接失败）：{len(hard_block_chapters)}章")
    print(f"  ⚠️  需LLM复核：{len(failed_chapters)}章")
    
    return all_results, failed_chapters, hard_block_chapters


def stage2_llm_review(failed_chapters: List[Dict], base: Path) -> List[Dict]:
    """第二阶段：LLM复核
    
    Returns:
        LLM评审结果列表
    """
    if not failed_chapters:
        return []
    
    print(f"🤖 第二阶段：LLM复核（{len(failed_chapters)}章）...")
    print("  ⏳ 正在调用LLM进行语义评审，请稍候...")
    
    llm_results = batch_llm_review(failed_chapters, str(base))
    
    # 统计结果
    agree_pass = sum(1 for r in llm_results if r.get("comparison") == "agree_pass")
    agree_fail = sum(1 for r in llm_results if r.get("comparison") == "agree_fail")
    disagree = sum(1 for r in llm_results if r.get("comparison") == "disagree")
    
    print(f"  ✅ LLM复核完成：")
    print(f"     - 脚本误报（LLM认为应通过）：{agree_pass}章")
    print(f"     - 确认失败（需重写）：{agree_fail}章")
    print(f"     - 判定不一致（需人工）：{disagree}章")
    
    return llm_results


def stage3_update_rules(llm_results: List[Dict], script_path: Path, 
                        force_update: bool = False) -> Dict:
    """第三阶段：自动更新规则
    
    Args:
        llm_results: LLM评审结果
        script_path: 脚本路径
        force_update: 是否强制更新（即使有不一致）
    
    Returns:
        更新统计
    """
    # 只处理一致认为通过的（误报）
    agree_pass_results = [r for r in llm_results if r.get("comparison") == "agree_pass"]
    
    if not agree_pass_results:
        print("📊 第三阶段：无需更新规则（没有一致认为误报的章节）")
        return {"rules_updated": 0}
    
    print(f"🔧 第三阶段：自动更新规则（{len(agree_pass_results)}个误报）...")
    
    stats = process_llm_results(agree_pass_results, script_path)
    
    print(f"  ✅ 规则更新完成：")
    print(f"     - 新增关键词：{stats['keywords_added']}个")
    print(f"     - 更新规则：{stats['rules_updated']}处")
    
    return stats


def generate_combined_report(all_results: List[Dict], llm_results: List[Dict],
                             update_stats: Dict, base: Path,
                             hard_block_chapters: List[Dict] = None) -> str:
    """生成综合报告"""
    r = []
    r.append("# 两阶段评审报告\n\n")
    r.append(f"**评审时间**：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
    
    # 第一阶段结果
    r.append("## 一、第一阶段：脚本检测结果\n\n")
    r.append(generate_report(all_results))
    
    # 硬阻断章节（直接失败，不需LLM复核）
    if hard_block_chapters:
        r.append("\n### 🔴 硬阻断章节（字数超标/不足，直接失败）\n\n")
        r.append("| 章节 | 字数 | 问题 |\n")
        r.append("|------|------|------|\n")
        for hb in hard_block_chapters:
            issues = "; ".join(hb.get("hard_blocks", []))
            r.append(f"| 第{hb['chapter']}章 | {hb.get('word_count', 0)}字 | {issues} |\n")
    
    # 第二阶段结果
    if llm_results:
        r.append("\n\n## 二、第二阶段：LLM复核结果\n\n")
        r.append("| 章节 | 脚本判定 | LLM判定 | 比较结果 | 说明 |\n")
        r.append("|------|----------|---------|----------|------|\n")
        
        for lr in llm_results:
            comparison_text = {
                "agree_pass": "✅ 脚本误报（LLM通过）",
                "agree_fail": "❌ 确认失败（需重写）",
                "disagree": "⚠️ 不一致（需人工）"
            }.get(lr.get("comparison", ""), "❓ 未知")
            
            summary = lr.get("summary", "")[:50]
            r.append(f"| {lr.get('chapter', '?')} | {lr.get('script_verdict', '?')} | "
                     f"{lr.get('llm_verdict', '?')} | {comparison_text} | {summary} |\n")
        
        # 误报详情
        false_positives = [r for r in llm_results if r.get("comparison") == "agree_pass"]
        if false_positives:
            r.append("\n### 误报详情\n\n")
            for fp in false_positives:
                r.append(f"**第{fp['chapter']}章**：\n")
                for fp_item in fp.get("false_positives", []):
                    r.append(f"- 问题：{fp_item['issue']}\n")
                    r.append(f"  依据：{fp_item['evidence']}\n")
                r.append("\n")
    
    # 第三阶段结果
    if update_stats.get("rules_updated", 0) > 0:
        r.append("\n\n## 三、第三阶段：规则更新结果\n\n")
        r.append(f"| 指标 | 数量 |\n|------|------|\n")
        r.append(f"| 新增关键词 | {update_stats.get('keywords_added', 0)} |\n")
        r.append(f"| 更新规则 | {update_stats.get('rules_updated', 0)} |\n\n")
    
    # 最终结论
    r.append("\n\n## 四、最终结论\n\n")
    
    # 统计最终结果
    final_pass = sum(1 for res in all_results if res.get("verdict") == "通过")
    final_fail = len(all_results) - final_pass
    
    # 从LLM结果中调整（agree_pass = 脚本误报，应算通过）
    for lr in llm_results:
        if lr.get("comparison") == "agree_pass":
            final_pass += 1
            final_fail -= 1
    
    hard_block_count = len(hard_block_chapters) if hard_block_chapters else 0
    llm_confirm_fail = sum(1 for r in llm_results if r.get("comparison") == "agree_fail")

    r.append(f"- **总章节数**：{len(all_results)}\n")
    r.append(f"- **最终通过**：{final_pass}章\n")
    r.append(f"- **最终失败**：{final_fail}章\n")
    r.append(f"  - 硬阻断（字数<3000或>6000）：{hard_block_count}章\n")
    r.append(f"  - LLM确认失败：{llm_confirm_fail}章\n")
    r.append(f"- **通过率**：{final_pass/len(all_results)*100:.1f}%\n\n")
    
    # 需要重写的章节
    rewrite_chapters = []
    for lr in llm_results:
        if lr.get("comparison") == "agree_fail":
            rewrite_chapters.append(lr["chapter"])
    
    if hard_block_chapters:
        r.append("\n### 🔴 硬阻断章节（字数问题，需拆分/扩充）\n\n")
        for hb in hard_block_chapters:
            issues = "; ".join(hb.get("hard_blocks", []))
            r.append(f"- 第{hb['chapter']}章：{issues}\n")
    
    if rewrite_chapters:
        r.append("\n### ❌ LLM确认失败章节（需重写）\n\n")
        for ch in sorted(rewrite_chapters):
            r.append(f"- 第{ch}章\n")
    
    return "".join(r)


def main():
    parser = argparse.ArgumentParser(description="两阶段评审脚本")
    parser.add_argument("--start", type=int, required=True, help="起始章节号")
    parser.add_argument("--end", type=int, required=True, help="结束章节号")
    parser.add_argument("--base-dir", type=str, default=str(DEFAULT_BASE),
                       help="小说根目录")
    parser.add_argument("--output", type=str, default="", help="报告输出路径")
    parser.add_argument("--update-rules", action="store_true", 
                       help="自动更新规则（默认不更新）")
    parser.add_argument("--report-only", action="store_true",
                       help="只生成报告，不执行LLM评审")
    parser.add_argument("--max-llm-chapters", type=int, default=20,
                       help="最大LLM评审章节数（避免过多API调用）")
    
    args = parser.parse_args()
    base = Path(args.base_dir)
    script_path = Path(__file__).parent / "batch_review.py"
    
    print("=" * 60)
    print("📚 两阶段评审系统")
    print("=" * 60)
    
    # 第一阶段：脚本检测
    all_results, failed_chapters, hard_block_chapters = stage1_script_review(args.start, args.end, base)
    
    # 如果只生成报告或没有失败章节，直接输出
    if args.report_only or not failed_chapters:
        report = generate_report(all_results)
        output_path = Path(args.output) if args.output else \
            base / "评审报告" / f"{datetime.now().date()}_第{args.start}-{args.end}章_脚本评审报告.md"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")
        print(f"\n📄 报告已保存：{output_path}")
        return
    
    # 限制LLM评审章节数
    if len(failed_chapters) > args.max_llm_chapters:
        print(f"⚠️  失败章节过多（{len(failed_chapters)}章），限制为前{args.max_llm_chapters}章")
        failed_chapters = failed_chapters[:args.max_llm_chapters]
    
    # 第二阶段：LLM复核
    llm_results = stage2_llm_review(failed_chapters, base)
    
    # 第三阶段：规则更新
    update_stats = {"rules_updated": 0}
    if args.update_rules:
        update_stats = stage3_update_rules(llm_results, script_path)
    
    # 生成综合报告
    combined_report = generate_combined_report(all_results, llm_results, update_stats, base, hard_block_chapters)
    
    output_path = Path(args.output) if args.output else \
        base / "评审报告" / f"{datetime.now().date()}_第{args.start}-{args.end}章_两阶段评审报告.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(combined_report, encoding="utf-8")
    
    print(f"\n📄 综合报告已保存：{output_path}")
    
    # 输出最终统计
    print("\n" + "=" * 60)
    print("📊 最终统计")
    print("=" * 60)
    
    final_pass = sum(1 for res in all_results if res.get("verdict") == "通过")
    for lr in llm_results:
        if lr.get("comparison") == "agree_pass":
            final_pass += 1
    
    total_fail = len(all_results) - final_pass
    hard_block_count = len(hard_block_chapters) if hard_block_chapters else 0
    llm_confirm_fail = sum(1 for r in llm_results if r.get("comparison") == "agree_fail")
    
    print(f"总章节：{len(all_results)}")
    print(f"最终通过：{final_pass}")
    print(f"最终失败：{total_fail}")
    print(f"  - 硬阻断（字数<3000或>6000）：{hard_block_count}章")
    print(f"  - LLM确认失败：{llm_confirm_fail}章")
    print(f"通过率：{final_pass/len(all_results)*100:.1f}%")
    
    if update_stats.get("rules_updated", 0) > 0:
        print(f"规则更新：{update_stats['rules_updated']}处")


if __name__ == "__main__":
    main()
