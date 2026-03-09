#!/usr/bin/env python3
"""
Self-Evolving Memory System - 接口层
提供策略检索、事件记录、学习等功能
"""

import json
import yaml
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

BASE_PATH = Path.home() / ".openclaw" / "memory-system"

class MemorySystem:
    """记忆管理系统"""
    
    def __init__(self):
        self.base_path = BASE_PATH
        self.strategies_path = self.base_path / "strategies"
        self.events_path = self.base_path / "events"
        self.index_path = self.base_path / "index.json"
        self.status_path = self.base_path / "status.json"
        self.governance_path = self.base_path / "governance.yaml"
        
        # 加载配置
        self._load_governance()
        self._load_index()
    
    def _load_governance(self):
        """加载治理配置"""
        try:
            with open(self.governance_path) as f:
                self.governance = yaml.safe_load(f)
        except:
            self.governance = {}
    
    def _load_index(self):
        """加载索引"""
        try:
            with open(self.index_path) as f:
                self.index = json.load(f)
        except:
            self.index = {"indexes": {"by_condition": {}, "by_context": {}}}
    
    # ============================================
    # 核心接口
    # ============================================
    
    def retrieve_strategies(self, context: Dict) -> List[Dict]:
        """
        检索相关策略
        
        Args:
            context: {"task": "...", "context": "...", ...}
        
        Returns:
            相关策略列表，按权重排序
        """
        strategies = []
        
        # 1. 从索引中匹配
        index = self.index.get("indexes", {})
        
        # 按条件匹配
        for cond, sid in index.get("by_condition", {}).items():
            if self._match_condition(cond, context):
                strategy = self._load_strategy(sid)
                if strategy:
                    strategies.append(strategy)
        
        # 按上下文匹配
        ctx_key = context.get("context", "")
        if ctx_key in index.get("by_context", {}):
            for sid in index["by_context"][ctx_key]:
                strategy = self._load_strategy(sid)
                if strategy and strategy not in strategies:
                    strategies.append(strategy)
        
        # 按权重排序
        strategies.sort(key=lambda x: x.get("weight", 0), reverse=True)
        
        return strategies
    
    def log_event(self, type: str, goal: str, context: Dict, 
                  action: str, outcome: str, feedback: str = None):
        """
        记录事件
        
        Args:
            type: 事件类型 (user_feedback | error | new_pattern | ...)
            goal: 任务目标
            context: 上下文
            action: 执行的动作
            outcome: 结果
            feedback: 用户反馈（可选）
        """
        # 检查是否在允许的类型中
        allowed = self.governance.get("events", {}).get("allowed_types", [])
        if allowed and type not in allowed:
            return  # 不记录
        
        # 检查容量
        if not self._check_capacity():
            self._run_cleanup()
        
        # 构建事件
        event = {
            "timestamp": datetime.now().isoformat(),
            "type": type,
            "goal": goal,
            "context": context,
            "action": action,
            "outcome": outcome
        }
        if feedback:
            event["feedback"] = feedback
        
        # 写入事件文件
        today = datetime.now().strftime("%Y-%m-%d")
        event_file = self.events_path / f"{today}.jsonl"
        
        with open(event_file, "a") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
        
        # 更新状态
        self._update_status()
    
    def learn_immediately(self, event: Dict) -> Optional[Dict]:
        """
        从事件中立即学习（生成策略）
        
        用于用户给出明确反馈时，立即生成策略
        """
        if event.get("type") != "user_feedback":
            return None
        
        feedback = event.get("feedback", "")
        if not feedback:
            return None
        
        # 简单的策略生成逻辑
        # TODO: 可以用 LLM 来提取更精确的策略
        strategy = {
            "id": f"auto-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "condition": event.get("goal", ""),
            "action": feedback,
            "weight": 0.8,
            "source": "user_feedback",
            "created": datetime.now().strftime("%Y-%m-%d"),
            "context": event.get("context", {})
        }
        
        # 保存策略
        self._save_strategy(strategy)
        
        return strategy
    
    def get_all_strategies(self) -> List[Dict]:
        """获取所有策略"""
        strategies = []
        
        for yaml_file in self.strategies_path.glob("*.yaml"):
            with open(yaml_file) as f:
                data = yaml.safe_load(f)
                if data:
                    for key in ["strategies", "preferences", "rules"]:
                        if key in data:
                            strategies.extend(data[key])
        
        return sorted(strategies, key=lambda x: x.get("weight", 0), reverse=True)
    
    # ============================================
    # 内部方法
    # ============================================
    
    def _load_strategy(self, sid: str) -> Optional[Dict]:
        """加载单个策略"""
        for yaml_file in self.strategies_path.glob("*.yaml"):
            with open(yaml_file) as f:
                data = yaml.safe_load(f)
                if not data:
                    continue
                for key in ["strategies", "preferences", "rules"]:
                    for item in data.get(key, []):
                        if item.get("id") == sid:
                            return item
        return None
    
    def _save_strategy(self, strategy: Dict):
        """保存策略到 task-strategies.yaml"""
        file_path = self.strategies_path / "task-strategies.yaml"
        
        with open(file_path) as f:
            data = yaml.safe_load(f) or {"strategies": []}
        
        data["strategies"].append(strategy)
        
        with open(file_path, "w") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
    
    def _match_condition(self, condition: str, context: Dict) -> bool:
        """匹配条件"""
        # 简单的关键词匹配
        ctx_str = " ".join(str(v) for v in context.values())
        return condition in ctx_str
    
    def _check_capacity(self) -> bool:
        """检查容量是否超限"""
        status = self._get_status()
        
        events_usage = status["usage"]["events"]["usage_percent"]
        strategies_usage = status["usage"]["strategies"]["usage_percent"]
        
        return events_usage < 80 and strategies_usage < 80
    
    def _get_status(self) -> Dict:
        """获取当前状态"""
        try:
            with open(self.status_path) as f:
                return json.load(f)
        except:
            return {"usage": {"events": {}, "strategies": {}}}
    
    def _update_status(self):
        """更新状态"""
        # 计算当前使用量
        events_size = 0
        events_count = 0
        for f in self.events_path.glob("*.jsonl"):
            events_size += f.stat().st_size
            with open(f) as fp:
                events_count += sum(1 for _ in fp)
        
        strategies_size = 0
        strategies_count = 0
        for f in self.strategies_path.glob("*.yaml"):
            strategies_size += f.stat().st_size
            with open(f) as fp:
                data = yaml.safe_load(fp)
                for key in ["strategies", "preferences", "rules"]:
                    strategies_count += len(data.get(key, []))
        
        # 更新状态文件
        status = self._get_status()
        status["usage"]["events"] = {
            "count": events_count,
            "size_kb": events_size // 1024,
            "usage_percent": events_count / 1000 * 100
        }
        status["usage"]["strategies"] = {
            "count": strategies_count,
            "size_kb": strategies_size // 1024,
            "usage_percent": strategies_count / 100 * 100
        }
        status["last_check"] = datetime.now().isoformat()
        
        with open(self.status_path, "w") as f:
            json.dump(status, f, indent=2)
    
    def _run_cleanup(self):
        """运行清理"""
        # TODO: 实现清理逻辑
        pass


# ============================================
# 便捷函数
# ============================================

_memory = None

def get_memory() -> MemorySystem:
    """获取单例实例"""
    global _memory
    if _memory is None:
        _memory = MemorySystem()
    return _memory


def retrieve_strategies(context: Dict) -> List[Dict]:
    """检索相关策略"""
    return get_memory().retrieve_strategies(context)


def log_event(type: str, goal: str, context: Dict, 
              action: str, outcome: str, feedback: str = None):
    """记录事件"""
    get_memory().log_event(type, goal, context, action, outcome, feedback)


def learn_immediately(event: Dict) -> Optional[Dict]:
    """立即学习"""
    return get_memory().learn_immediately(event)


if __name__ == "__main__":
    # 测试
    m = get_memory()
    
    print("=== 所有策略 ===")
    for s in m.get_all_strategies():
        print(f"  [{s.get('weight', 0):.2f}] {s.get('condition', '')} → {s.get('action', '')[:30]}...")
    
    print("\n=== 检索测试 ===")
    ctx = {"task": "小红书发布", "context": "小红书发布"}
    results = m.retrieve_strategies(ctx)
    print(f"匹配到 {len(results)} 条策略")
    for r in results:
        print(f"  - {r.get('condition')}")