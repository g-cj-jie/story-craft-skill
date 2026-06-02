#!/usr/bin/env python3
"""
规则自动扩充模块
根据LLM评审结果，自动扩充脚本的检测规则
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Tuple


# 脚本中各检测函数的位置标记
SCRIPT_MARKER = {
    "key_scenes": "# KEY_SCENES_RULES",
    "ending_hooks": "# ENDING_HOOK_RULES",
    "foreshadowing": "# FORESHADOWING_RULES",
    "world_items": "# WORLD_ITEMS_RULES",
    "other_world": "# OTHER_WORLD_RULES"
}


def extract_keywords_from_evidence(evidence: str) -> List[str]:
    """从LLM的判断依据中提取关键词
    
    例如：
    - "正文中出现'苏晨用铁剑劈砍'，包含了挥剑攻击的含义" 
      → ["苏晨用铁剑劈砍", "劈砍"]
    - "结尾'苏晨握紧了拳头，眼中闪过一丝决绝'暗示了决心，构成隐晦钩子"
      → ["握紧了拳头", "眼中闪过", "决绝"]
    """
    keywords = []
    
    # 提取引号中的内容
    quoted = re.findall(r"[「「](.+?)[」」]", evidence)
    keywords.extend(quoted)
    
    # 提取"包含""出现""使用"后面的内容
    patterns = [
        r"包含[了]?(.+?)(?:的|，|。|$)",
        r"出现[了]?(.+?)(?:，|。|$)",
        r"使用[了]?(.+?)(?:，|。|$)",
        r"通过(.+?)(?:表达|暗示|体现|展现)",
    ]
    for pattern in patterns:
        matches = re.findall(pattern, evidence)
        keywords.extend(matches)
    
    # 清理和去重
    cleaned = []
    for kw in keywords:
        kw = kw.strip()
        if len(kw) >= 2 and kw not in cleaned:
            cleaned.append(kw)
    
    return cleaned


def categorize_issue(issue: str) -> str:
    """分类问题类型"""
    if "关键场景" in issue:
        return "key_scenes"
    elif "结尾钩子" in issue:
        return "ending_hooks"
    elif "伏笔" in issue:
        return "foreshadowing"
    elif "现代物品" in issue:
        return "world_items"
    elif "其他世界" in issue:
        return "other_world"
    return "unknown"


def generate_rule_update(issue: str, evidence: str, category: str) -> Tuple[str, List[str]]:
    """生成规则更新代码
    
    Returns:
        (更新类型, 新关键词列表)
    """
    keywords = extract_keywords_from_evidence(evidence)
    
    if not keywords:
        return "no_update", []
    
    return category, keywords


def apply_updates_to_script(script_path: Path, updates: List[Dict]) -> str:
    """将更新应用到脚本
    
    Args:
        script_path: 脚本路径
        updates: 更新列表，每项包含:
            - category: 规则类别
            - keywords: 新关键词列表
            - issue: 原始问题描述
            - evidence: LLM判断依据
    
    Returns:
        更新后的脚本内容
    """
    content = script_path.read_text(encoding="utf-8")
    
    for update in updates:
        category = update["category"]
        keywords = update["keywords"]
        
        if category == "key_scenes":
            # 扩充关键场景同义词映射
            # 找到 KEY_SCENE_SYNONYMS 字典
            synonyms_pattern = r"KEY_SCENE_SYNONYMS\s*=\s*\{([^}]*)\}"
            match = re.search(synonyms_pattern, content, re.DOTALL)
            if match:
                existing = match.group(1).strip()
                # 添加新的同义词映射
                new_entries = []
                for kw in keywords:
                    new_entries.append(f'    "{kw}": ["{kw}", "{kw}变体"],')
                
                if existing:
                    new_content = existing + "\n" + "\n".join(new_entries)
                else:
                    new_content = "\n".join(new_entries)
                
                content = content.replace(
                    match.group(0),
                    f"KEY_SCENE_SYNONYMS = {{\n{new_content}\n}}"
                )
        
        elif category == "ending_hooks":
            # 扩充结尾钩子关键词
            hooks_pattern = r'hooks\s*=\s*\[([^\]]+)\]'
            match = re.search(hooks_pattern, content)
            if match:
                existing_hooks = match.group(1)
                # 提取现有关键词
                existing_keywords = re.findall(r'"([^"]+)"', existing_hooks)
                
                # 添加新关键词
                for kw in keywords:
                    if kw not in existing_keywords:
                        existing_keywords.append(kw)
                
                # 重新生成hooks列表
                new_hooks = ", ".join(f'"{kw}"' for kw in existing_keywords)
                content = content.replace(
                    match.group(0),
                    f'hooks = [{new_hooks}]'
                )
        
        elif category == "world_items":
            # 扩充现代物品关键词
            items_pattern = r'for item in \[([^\]]+)\]:'
            match = re.search(items_pattern, content)
            if match:
                existing_items = match.group(1)
                existing_keywords = re.findall(r'"([^"]+)"', existing_items)
                
                for kw in keywords:
                    if kw not in existing_keywords:
                        existing_keywords.append(kw)
                
                new_items = ", ".join(f'"{kw}"' for kw in existing_keywords)
                content = content.replace(
                    match.group(0),
                    f'for item in [{new_items}]:'
                )
        
        elif category == "other_world":
            # 扩充其他世界内容关键词
            world_pattern = r'for w in \[([^\]]+)\]:'
            match = re.search(world_pattern, content)
            if match:
                existing_worlds = match.group(1)
                existing_keywords = re.findall(r'"([^"]+)"', existing_worlds)
                
                for kw in keywords:
                    if kw not in existing_keywords:
                        existing_keywords.append(kw)
                
                new_worlds = ", ".join(f'"{kw}"' for kw in existing_keywords)
                content = content.replace(
                    match.group(0),
                    f'for w in [{new_worlds}]:'
                )
    
    return content


def save_update_log(log_path: Path, updates: List[Dict]):
    """保存更新日志"""
    log_entry = {
        "timestamp": __import__('datetime').datetime.now().isoformat(),
        "updates": updates
    }
    
    # 追加到日志文件
    if log_path.exists():
        try:
            logs = json.loads(log_path.read_text(encoding="utf-8"))
        except:
            logs = []
    else:
        logs = []
    
    logs.append(log_entry)
    log_path.write_text(json.dumps(logs, ensure_ascii=False, indent=2), encoding="utf-8")


def process_llm_results(llm_results: List[Dict], script_path: Path) -> Dict:
    """处理LLM评审结果，生成规则更新
    
    Args:
        llm_results: LLM评审结果列表
        script_path: 脚本路径
    
    Returns:
        处理结果统计
    """
    updates = []
    stats = {
        "total_reviews": len(llm_results),
        "false_positives": 0,
        "confirmed_failures": 0,
        "rules_updated": 0,
        "keywords_added": 0
    }
    
    for result in llm_results:
        if result.get("comparison") == "agree_pass":
            # LLM认为通过，脚本误报
            stats["false_positives"] += 1
            
            for fp in result.get("false_positives", []):
                category = categorize_issue(fp["issue"])
                if category != "unknown":
                    update_type, keywords = generate_rule_update(
                        fp["issue"], fp["evidence"], category
                    )
                    if update_type != "no_update":
                        updates.append({
                            "category": category,
                            "keywords": keywords,
                            "issue": fp["issue"],
                            "evidence": fp["evidence"]
                        })
                        stats["keywords_added"] += len(keywords)
        
        elif result.get("comparison") == "agree_fail":
            # 两者都认为失败，确认需要重写
            stats["confirmed_failures"] += 1
    
    # 应用更新
    if updates:
        updated_content = apply_updates_to_script(script_path, updates)
        script_path.write_text(updated_content, encoding="utf-8")
        stats["rules_updated"] = len(updates)
        
        # 保存更新日志
        log_path = script_path.parent / "rules_update_log.json"
        save_update_log(log_path, updates)
    
    return stats


def generate_update_report(stats: Dict, updates: List[Dict]) -> str:
    """生成更新报告"""
    r = []
    r.append("# 规则自动扩充报告\n\n")
    r.append(f"**时间**: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
    r.append("## 统计\n\n")
    r.append(f"| 指标 | 数量 |\n|------|------|\n")
    r.append(f"| LLM评审章节数 | {stats['total_reviews']} |\n")
    r.append(f"| 确认误报数 | {stats['false_positives']} |\n")
    r.append(f"| 确认失败数 | {stats['confirmed_failures']} |\n")
    r.append(f"| 规则更新数 | {stats['rules_updated']} |\n")
    r.append(f"| 新增关键词数 | {stats['keywords_added']} |\n\n")
    
    if updates:
        r.append("## 更新详情\n\n")
        for i, update in enumerate(updates, 1):
            r.append(f"### 更新 {i}\n")
            r.append(f"- **类别**: {update['category']}\n")
            r.append(f"- **原始问题**: {update['issue']}\n")
            r.append(f"- **LLM依据**: {update['evidence']}\n")
            r.append(f"- **新增关键词**: {', '.join(update['keywords'])}\n\n")
    
    return "".join(r)


if __name__ == "__main__":
    # 测试用例
    test_results = [
        {
            "chapter": 54,
            "comparison": "agree_pass",
            "false_positives": [
                {
                    "issue": "缺少1个关键场景",
                    "evidence": "正文中出现'苏晨用铁剑劈砍'，包含了挥剑攻击的含义"
                }
            ]
        }
    ]
    
    script_path = Path(__file__).parent / "batch_review.py"
    stats = process_llm_results(test_results, script_path)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
