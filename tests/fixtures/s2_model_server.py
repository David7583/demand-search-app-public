"""S2 synthetic provider server. No real credentials or external model calls are accepted."""

import argparse
import json
import re
import sys
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps/server/src"))

from demand_search.config import Settings  # noqa: E402
from demand_search.errors import AppError  # noqa: E402
from demand_search.main import create_app  # noqa: E402
from demand_search.providers import ProviderClient  # noqa: E402


def collaboration_fixture(text, previous, parsed):
    """Fixed scenario contracts only: these do not measure a real model's reasoning."""
    strategy, task = "execute_first", "shopping"
    reply = (
        "我先整理可直接使用的清单，并准备官方搜索关键词。这里只提供搜"
        "索入口，没有真实商品价格或库存。"
    )
    assumptions, options = [], []
    steps = ["检查清单中的条件", "确认后去原平台继续搜索"]
    questions = []
    if "SYNTHETIC_HOME" in text or (
        "SYNTHETIC_FEEDBACK" in text
        and previous.get("collaboration", {}).get("task_type") == "planning"
    ):
        strategy, task = "plan_first", "planning"
        reply = (
            "先给你一份可讨论的初步方案：优先改善照明与收纳，保留可移动家具，把不可"
            "逆施工放到专业核实之后。下面是两个可比较的路径，估算仅用于讨论，并非商"
            "家报价。"
        )
        if "SYNTHETIC_FEEDBACK" in text:
            reply = (
                "根据你减少装饰、优先实用的反馈，我把方案调整为先照明和收纳，"
                "再决定软装。旧方案仍可查看，预算估算还未成为你的预算承诺。"
            )
        assumptions = ["暂按不改变结构的轻量改善考虑，面积和现状未核实"]
        options = [
            {
                "option_id": "light",
                "title": "先做轻量改善",
                "summary": "从可移动照明、收纳和家具布局入手。",
                "steps": ["盘点现有家具和采光", "先在一个区域试用布局", "根据反馈逐步扩展"],
                "tradeoffs": ["改动可逆，但无法解决结构或管线问题"],
                "budget_estimate": {
                    "low": 3000,
                    "high": 8000,
                    "currency": "CNY",
                    "basis": "合成示例：小范围软装",
                    "note": "合成讨论估算，未询价，地区、面积和材料会影响费用",
                },
            },
            {
                "option_id": "phased",
                "title": "分阶段整体规划",
                "summary": "先明确空间功能，再找专业人员评估施工。",
                "steps": ["列出优先改善的生活场景", "核实房屋条件", "再申请实际报价"],
                "tradeoffs": ["规划时间更长，但可以减少返工"],
                "budget_estimate": None,
            },
        ]
        steps, questions = (
            ["选择最值得先改善的区域", "先试可逆调整"],
            ["你最想优先改善哪个生活场景？"],
        )
        parsed.update(
            items=[],
            budget_ceiling=None,
            required=[],
            preferred=[],
            unknown=["实际面积和报价未核实"],
            desired_outcome="形成可逐步迭代的居住改善方案",
        )
    elif "SYNTHETIC_EXPLORE" in text:
        strategy, task = "explore_first", "exploration"
        reply = (
            "你还不需要先确定要买什么。可以从减少家务、改善工作舒适度两个"
            "方向试探，先挑一个最贴近生活的问题，我们再一起形成方案。"
        )
        options = [
            {
                "option_id": "chores",
                "title": "减少日常家务",
                "summary": "先观察最重复和耗时的环节。",
                "steps": ["记录一次家务流程"],
                "tradeoffs": ["未必需要购买新商品"],
                "budget_estimate": None,
            },
            {
                "option_id": "comfort",
                "title": "改善工作舒适度",
                "summary": "从坐姿、照明和收纳观察。",
                "steps": ["找出最不舒服的一件事"],
                "tradeoffs": ["先验证实际原因"],
                "budget_estimate": None,
            },
        ]
        steps, questions = ["挑一个方向做小尝试"], ["最近哪件小事最让你觉得麻烦？"]
        parsed.update(
            items=[],
            budget_ceiling=None,
            required=[],
            preferred=[],
            unknown=["目标方向未选定"],
            desired_outcome="探索适合自己的生活改善方向",
        )
    elif "SYNTHETIC_SEARCH" in text:
        reply = (
            "按你明确的条件整理办公椅搜索入口。预算1500 CNY是你的"
            "上限，不是已查到的价格；没有连接商品数据源。确认条件后可直接"
            "去原平台继续搜索。"
        )
        parsed.update(
            desired_outcome="找到符合明确条件的办公椅",
            required=[],
            preferred=[],
            unknown=[],
            budget_ceiling={
                "amount": 1500,
                "currency": "CNY",
                "source": "user_explicit",
                "evidence": "1500 CNY",
            },
            items=[
                {
                    "item_id": None,
                    "name": "办公椅",
                    "quantity": None,
                    "unit": None,
                    "source": "user_explicit",
                    "evidence": "办公椅",
                    "required": [],
                    "preferred": [],
                    "unknown": [],
                    "budget_ceiling": None,
                    "budget_basis": "unknown",
                    "status": "active",
                }
            ],
        )
    elif "SYNTHETIC_RISK" in text:
        strategy, task = "verify_first", "planning"
        reply = (
            "涉及拆改承重结构，不能凭聊天判断可以施工。先核对图纸和专业鉴"
            "定；现在可以整理需要咨询的问题，暂不提供拆除操作步骤。"
        )
        steps, questions = (
            ["暂停拆改，向有资质的专业人员核实"],
            ["是否已有结构图纸和专业鉴定意见？"],
        )
        parsed.update(
            items=[],
            budget_ceiling=None,
            required=[],
            preferred=[],
            unknown=["结构安全未核实"],
            desired_outcome="在专业核实后再决定施工方案",
        )
    parsed.update(clarification_questions=questions, possible_new_intent=False)
    collaboration = {
        "strategy": strategy,
        "rationale": "合成测试：根据目标清晰度、风险与可行动性选择。",
        "task_type": task,
        "assumptions": assumptions,
        "options": options,
        "next_steps": steps,
        "limitations": ["合成测试建议，未访问商品、报价或供应商数据。"],
        "needs_verification": strategy == "verify_first",
    }
    # assistant_reply is deliberately first for incremental JSON text extraction.
    return {"assistant_reply": reply, "collaboration": collaboration, **parsed}


class SyntheticDemandProvider(ProviderClient):
    def request_json(self, base_url, provider, api_key, method, path, body=None):
        if provider != "custom" or not api_key.startswith("synthetic-s2-only-"):
            raise AppError("SYNTHETIC_FIXTURE_ONLY", "Only synthetic S2 credentials accepted.")
        if method == "GET":
            return {"data": [{"id": "synthetic-s2"}]}
        if body.get("model") == "synthetic-failure":
            raise AppError("PROVIDER_TIMEOUT", "Synthetic S2 provider timeout.", 504)
        prompt = (body.get("messages") or body.get("input"))[-1]["content"]
        if prompt.startswith("{"):
            value = json.loads(prompt)
            text = value["current_message"]
            previous = value.get("current_draft") or value.get("confirmed_demand") or {}
            amount = 3000 if "3000" in text else 1500
            evidence = "预算3000元" if amount == 3000 else "预算1500元"
            parsed = {
                "items": [],
                "desired_outcome": previous.get("desired_outcome", "适合久坐的办公椅"),
                "required": [{"text": "久坐", "source": "user_explicit", "evidence": "适合久坐"}],
                "preferred": [],
                "unknown": ["座位尺寸尚未确认"],
                "budget_ceiling": {
                    "amount": amount,
                    "currency": "CNY",
                    "source": "user_explicit",
                    "evidence": evidence,
                },
                "readiness": "need",
                "alternatives_acceptable": None,
                "clarification_questions": ["座位尺寸有要求吗？"],
                "possible_new_intent": "显示器" in text,
            }
            if "SYNTHETIC_LIST_20" in text or "SYNTHETIC_LIST_CHANGE" in text:

                def item(name, item_id=None):
                    return {
                        "item_id": item_id,
                        "name": name,
                        "quantity": 1,
                        "unit": "件",
                        "source": "user_explicit",
                        "evidence": name,
                        "required": [],
                        "preferred": [],
                        "unknown": [],
                        "budget_ceiling": None,
                        "budget_basis": "unknown",
                        "status": "active",
                    }

                if "SYNTHETIC_LIST_20" in text:
                    items = [item("合成物品" + str(index).zfill(2)) for index in range(1, 21)]
                    total = 5000
                else:
                    items = []
                    for previous_item in previous.get("items", []):
                        row = item(previous_item["name"], previous_item["item_id"])
                        if row["name"] == "合成物品01":
                            row["budget_ceiling"] = {
                                "amount": 300,
                                "currency": "CNY",
                                "source": "user_explicit",
                                "evidence": "合成物品01每件预算300 CNY",
                            }
                            row["budget_basis"] = "unit"
                        if row["name"] == "合成物品02":
                            row["status"] = "removed"
                        items.append(row)
                    items.append(item("合成物品21"))
                    total = 6000
                parsed.update(
                    {
                        "items": items,
                        "desired_outcome": "合成多物品测试清单",
                        "required": [],
                        "preferred": [],
                        "unknown": [],
                        "budget_ceiling": {
                            "amount": total,
                            "currency": "CNY",
                            "source": "user_explicit",
                            "evidence": "总预算" + str(total) + " CNY",
                        },
                        "alternatives_acceptable": None,
                        "clarification_questions": [],
                        "possible_new_intent": False,
                    }
                )
        else:
            parsed = {
                "desired_outcome": "synthetic setup preview",
                "required": [],
                "preferred": [],
                "unknown": [],
            }
        if body.get("stream") and prompt.startswith("{"):
            if "SYNTHETIC_REFERENCE" in text:
                reference = value.get("referenced_version")
                if not reference or not isinstance(reference.get("data"), dict):
                    raise AppError(
                        "SYNTHETIC_REFERENCE_MISSING",
                        "Synthetic referenced context was absent.",
                        502,
                    )
                options = reference["data"].get("collaboration", {}).get("options", [])
                if not options:
                    raise AppError(
                        "SYNTHETIC_REFERENCE_MISSING",
                        "Synthetic referenced options were absent.",
                        502,
                    )
                parsed = collaboration_fixture("SYNTHETIC_HOME", previous, parsed)
                parsed["assistant_reply"] = (
                    "合成测试：已读取引用版本 "
                    + str(reference["number"])
                    + "："
                    + options[0]["summary"]
                    + "。仅供讨论，沿当前版本继续迭代。"
                )
            else:
                parsed = collaboration_fixture(text, previous, parsed)
        content = json.dumps(parsed, ensure_ascii=False)
        if "messages" in body:
            return {
                "model": "synthetic-s2-actual",
                "choices": [{"finish_reason": "stop", "message": {"content": content}}],
            }
        return {
            "model": "synthetic-s2-actual",
            "status": "completed",
            "output": [{"type": "message", "content": [{"type": "output_text", "text": content}]}],
        }

    def request_stream(self, base_url, provider, api_key, path, body, on_delta):
        # Synthetic upstream chunks, real domain/HTTP/browser streaming afterwards.
        result = self.request_json(base_url, provider, api_key, "POST", path, body)
        if "choices" in result:
            content = result["choices"][0]["message"]["content"]
        else:
            content = result["output"][0]["content"][0]["text"]
        prompt = (body.get("messages") or body.get("input"))[-1]["content"]
        fail = "SYNTHETIC_STREAM_FAILURE" in prompt
        for index in range(0, len(content), 97):
            on_delta(content[index : index + 97])
            time.sleep(0.012)
            if "SYNTHETIC_STREAM_SLOW" in prompt and index == 194:
                time.sleep(0.65)
            if fail and index >= 194:
                raise AppError("PROVIDER_STREAM_INTERRUPTED", "Synthetic interrupted stream.", 502)
        return result


def main():
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=18000)
    parser.add_argument("--data-subdir", default="test-s2-browser-" + uuid4().hex)
    args = parser.parse_args()
    if args.port == 8000 or not 1024 <= args.port <= 65535:
        raise SystemExit("Synthetic fixture cannot bind the user application port.")
    if not re.fullmatch(r"test-s2-(?:browser|http)-[0-9a-f]{32}", args.data_subdir):
        raise SystemExit("A dedicated synthetic S2 data directory is required.")
    settings = Settings(data_dir=ROOT / "runtime" / args.data_subdir)
    app = create_app(
        settings,
        provider_client=SyntheticDemandProvider(),
        client_assets=ROOT / ".local/s2-client/h5",
    )
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=args.port,
        proxy_headers=False,
        access_log=False,
        log_level="error",
    )


if __name__ == "__main__":
    main()
