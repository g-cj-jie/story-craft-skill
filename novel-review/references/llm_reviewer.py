#!/usr/bin/env python3
"""
LLM二次评审模块
对脚本判定失败的章节，调用LLM进行语义评审
输出：与脚本判定是否一致 + 评审依据
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import requests
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
    import requests


# API配置（从hermes config读取，或使用默认值）
API_CONFIG = {
    "base_url": "https://open.bigmodel.cn/api/paas/v4",
    "api_key": "7de6e518f13b4301bc816ddb4ece8efc.sB2YSGUR29Dh9hkv",
    "model": "glm-4-flash-250414",
}


def build_review_prompt(chapter_num: int, chapter_content: str,
                        outline_content: str, script_issues: List[str]) -> str:
    """构建LLM评审提示词"""
    # 截取正文前4000字避免token过多
    content_preview = chapter_content[:4000]
    outline_preview = outline_content[:2000]

    prompt = f"""你是一个专业的网络小说评审专家。请评审以下章节，判断脚本检测到的问题是否为误报。

## 章节信息
- 章节号：第{chapter_num}章
- 字数：{len(chapter_content)}字

## 章纲内容
{outline_preview}

## 正文内容（前4000字）
{content_preview}

## 脚本检测到的问题
{json.dumps(script_issues, ensure_ascii=False, indent=2)}

## 评审任务
请判断脚本检测到的每个问题是否为**误报**（即正文实际包含相关内容，只是表述不同）。

对每个问题，请输出：
1. **问题描述**：脚本检测到的问题
2. **是否误报**：true/false
3. **判断依据**：如果误报，请指出正文中实际包含的内容（引用原文片段）；如果不是误报，请说明为什么确实缺失
4. **建议修改**：如果不是误报，给出具体修改建议

## 输出格式（严格JSON）
```json
{{
  "chapter": {chapter_num},
  "reviews": [
    {{
      "issue": "问题描述",
      "is_false_positive": true或false,
      "evidence": "判断依据（引用原文或说明缺失原因）",
      "suggestion": "修改建议（如果不是误报则填写，是误报则留空）"
    }}
  ],
  "overall_verdict": "pass或fail",
  "summary": "整体评价（一句话）"
}}
```

请严格按照JSON格式输出，不要添加任何其他内容。"""

    return prompt


def call_llm(prompt: str) -> str:
    """调用LLM进行评审（使用智谱API）"""
    url = f"{API_CONFIG['base_url']}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_CONFIG['api_key']}"
    }
    payload = {
        "model": API_CONFIG["model"],
        "messages": [
            {"role": "system", "content": "你是一个专业的网络小说评审专家，擅长判断内容是否符合章纲要求。请严格按照要求的JSON格式输出。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 2000
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        return json.dumps({"error": f"LLM调用失败: {str(e)}"})


def parse_llm_response(response: str) -> Optional[Dict]:
    """解析LLM返回的JSON"""
    try:
        # 尝试提取JSON部分
        start = response.find('{')
        end = response.rfind('}') + 1
        if start != -1 and end != -1:
            json_str = response[start:end]
            return json.loads(json_str)
    except json.JSONDecodeError:
        pass
    return None


def review_chapter_llm(chapter_num: int, chapter_content: str,
                       outline_content: str, script_issues: List[str]) -> Dict:
    """对单个章节进行LLM评审"""
    prompt = build_review_prompt(chapter_num, chapter_content, outline_content, script_issues)
    response = call_llm(prompt)
    result = parse_llm_response(response)

    if result is None:
        return {
            "chapter": chapter_num,
            "error": "LLM响应解析失败",
            "raw_response": response[:500]
        }

    return result


def compare_results(script_verdict: str, llm_verdict: str) -> str:
    """比较脚本和LLM的判定结果

    Returns:
        "agree_pass": 脚本误报（LLM认为通过）→ 需更新规则
        "agree_fail": 两者都认为失败 → 确认失败，需重写
        "disagree": LLM认为失败但脚本认为通过 → 异常情况
    """
    script_pass = script_verdict == "通过"
    llm_pass = llm_verdict == "pass"

    if script_pass and llm_pass:
        return "agree_pass"  # 两者都认为通过
    elif not script_pass and llm_pass:
        return "agree_pass"  # 脚本失败但LLM认为通过 → 误报！
    elif not script_pass and not llm_pass:
        return "agree_fail"  # 两者都认为失败
    else:
        return "disagree"  # 脚本通过但LLM认为失败 → 异常


def batch_llm_review(failed_chapters: List[Dict], base_dir: str) -> List[Dict]:
    """批量LLM评审

    Args:
        failed_chapters: 脚本判定失败的章节列表，每项包含:
            - chapter: 章节号
            - issues: 问题列表
            - script_verdict: 脚本判定结果
        base_dir: 小说根目录

    Returns:
        评审结果列表
    """
    base = Path(base_dir)
    results = []
    total = len(failed_chapters)

    for idx, ch_data in enumerate(failed_chapters):
        chapter_num = ch_data["chapter"]
        chapter_file = base / "章节正文" / f"第{chapter_num}章.md"
        outline_file = base / "故事大纲" / "章纲" / f"ch-{chapter_num}.md"

        print(f"    [{idx+1}/{total}] 第{chapter_num}章 LLM评审中...", end="", flush=True)

        if not chapter_file.exists() or not outline_file.exists():
            print(" ❌ 文件不存在")
            results.append({
                "chapter": chapter_num,
                "error": "文件不存在",
                **ch_data
            })
            continue

        chapter_content = chapter_file.read_text(encoding="utf-8")
        outline_content = outline_file.read_text(encoding="utf-8")

        llm_result = review_chapter_llm(
            chapter_num, chapter_content, outline_content, ch_data["issues"]
        )

        if "error" in llm_result:
            print(f" ❌ {llm_result['error']}")
            results.append({
                "chapter": chapter_num,
                "script_verdict": ch_data["script_verdict"],
                "llm_verdict": "error",
                "comparison": "disagree",
                "error": llm_result["error"],
                "raw_response": llm_result.get("raw_response", "")
            })
            continue

        comparison = compare_results(
            ch_data["script_verdict"],
            llm_result["overall_verdict"]
        )

        # 提取误报
        false_positives = []
        if comparison == "agree_pass":
            for review in llm_result.get("reviews", []):
                if review.get("is_false_positive"):
                    false_positives.append({
                        "issue": review["issue"],
                        "evidence": review.get("evidence", "")
                    })

        comparison_icon = {"agree_pass": "✅误报", "agree_fail": "❌确认", "disagree": "⚠️分歧"}
        print(f" {comparison_icon.get(comparison, '?')}")

        results.append({
            "chapter": chapter_num,
            "script_verdict": ch_data["script_verdict"],
            "llm_verdict": llm_result["overall_verdict"],
            "comparison": comparison,
            "llm_reviews": llm_result.get("reviews", []),
            "false_positives": false_positives,
            "summary": llm_result.get("summary", "")
        })

    return results


if __name__ == "__main__":
    # 测试
    test_chapters = [
        {
            "chapter": 54,
            "issues": ["字数严重超标：8045字（>6000字）"],
            "script_verdict": "需修改"
        }
    ]
    results = batch_llm_review(test_chapters, str(Path("/mnt/e/AI项目工程/小说/艾泽拉斯：死灵法师之路")))
    print(json.dumps(results, ensure_ascii=False, indent=2))
