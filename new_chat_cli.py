import json
import os
import requests
from pydantic import ValidationError
from new_schemas import Character


def _get_api_key() -> str:
    try:
        import streamlit as st
        return st.secrets.get("ANTHROPIC_API_KEY", "") or os.environ.get("ANTHROPIC_API_KEY", "")
    except Exception:
        return os.environ.get("ANTHROPIC_API_KEY", "")


def _get_base_url() -> str:
    try:
        import streamlit as st
        return (st.secrets.get("ANTHROPIC_BASE_URL", "") or os.environ.get("ANTHROPIC_BASE_URL", "https://b.onerouter.com/api")).rstrip("/")
    except Exception:
        return os.environ.get("ANTHROPIC_BASE_URL", "https://b.onerouter.com/api").rstrip("/")


def call_model(messages: list, system_prompt: str):
    api_key = _get_api_key()
    base_url = _get_base_url()
    payload = {
        "model": "claude-opus-4-6",
        "max_tokens": 512,
        "system": system_prompt,
        "messages": messages,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    resp = requests.post(f"{base_url}/v1/messages", headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()


HISTORY_FILE = "new_chat_history.json"


def extract_json(text: str) -> str:
    """从 LLM 返回文本中提取 JSON 字符串"""
    text = text.strip()
    if "```" in text:
        parts = text.split("```")
        for i, part in enumerate(parts):
            stripped = part.strip()
            if stripped.startswith("json"):
                return stripped[4:].strip()
            elif i > 0 and stripped:
                return stripped
    return text


def load_history() -> list:
    """从文件加载历史对话记录"""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []
    return []


def save_history(history: list) -> None:
    """把历史对话记录保存到文件"""
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def generate_testcase(description: str, history: list, max_retries: int = 3) -> dict | None:
    """
    调用 Claude API 校验并提取商品信息，生成 JSON 测试用例，最多重试 max_retries 次。
    所有失败情况（乱码/无意义/语境不符/字段缺失/解析错误）统一返回 None 并提示解析失败。
    携带历史对话记录，支持多轮对话上下文。
    """
    system_prompt = """你是一个严格的角色信息提取器。

【处理规则】
第一步：判断输入是否有效
- 如果输入是乱码、无意义字符、与角色信息完全无关的内容，直接输出：{"error": "parse_failed"}

第二步：提取角色字段（仅当输入有效时执行）
- 只能提取描述中明确给出的信息，绝对禁止猜测、推断或自行编造任何字段值
- 用户可能分多轮补充信息，请结合历史对话中已提供的字段
- 必须同时包含全部 8 个字段才算成功：
  - code_name: str（角色代号，2-10个字符，不能含空格）
  - real_name: str（角色真名，至少2个字符）
  - faction: str（所属阵营，只能是以下之一："欧泊"、"剪刀手"、"防卫队"、"未知"）
  - role: str（战术定位，只能是以下之一："决斗"、"控场"、"先锋"、"支援"）
  - max_hp: int（最大生命值，1-200）
  - current_hp: int（当前生命值，大于等于0）
  - passive: str（被动技能名称）
  - tactical: str（战术技能名称）
  - ultimate: str（终极技能名称）
- 任何一个字段在描述中没有明确给出，输出：{"error": "parse_failed"}
- 不判断字段值是否合法，原样提取即可

第三步：输出结果
- 成功时只输出 JSON，不包含任何其他文字
- 失败时输出：{"error": "parse_failed"}"""

    # 在历史记录基础上追加当前输入
    messages = history + [{"role": "user", "content": description}]

    for attempt in range(1, max_retries + 1):
        try:
            response = call_model(messages=messages, system_prompt=system_prompt)
            content_blocks = response.get("content", [])
            text_parts = [b.get("text", "") for b in content_blocks if b.get("type") == "text"]
            content = "\n".join([t for t in text_parts if t]).strip()
            if not content:
                raise ValueError("empty_response")
            json_str = extract_json(content)
            parsed = json.loads(json_str)

            if parsed.get("error") == "parse_failed":
                raise ValueError("parse_failed")

            return parsed

        except Exception as e:
            if attempt < max_retries:
                print(f"  [解析失败] 第 {attempt} 次，正在重试... 原因: {e}")
            else:
                print(f"  [解析失败] 已尝试 {max_retries} 次，解析失败，返回主页面。原因: {e}")
                return None

    return None


def validate_and_save(testcase: dict, filename: str = "new_testcases.json") -> Character:
    """用 Pydantic 校验测试用例并追加保存到 JSON 文件"""
    commodity = Character(**testcase)

    existing: list = []
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            existing = []

    existing.append(commodity.model_dump())

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    return commodity


def main():
    print("=== Claude 角色测试用例生成器 ===")
    print("输入角色描述，将生成符合 Character schema 的 JSON 测试用例")
    print("输入 'history' 查看历史对话  |  输入 'clear' 清除历史  |  输入 'quit' 退出\n")

    # 启动时加载历史记录
    history = load_history()
    if history:
        print(f"[已加载 {len(history) // 2} 轮历史对话]\n")

    while True:
        description = input("请输入角色描述: ").strip()

        if description.lower() == "quit":
            print("退出程序")
            break

        if description.lower() == "history":
            if not history:
                print("暂无历史对话记录\n")
            else:
                print("\n─── 历史对话记录 ───")
                for msg in history:
                    role = "你" if msg["role"] == "user" else "Claude"
                    print(f"[{role}] {msg['content']}")
                print("────────────────────\n")
            continue

        if description.lower() == "clear":
            history = []
            save_history(history)
            print("历史对话已清除\n")
            continue

        if not description:
            print("描述不能为空\n")
            continue

        try:
            testcase = generate_testcase(description, history)
            if testcase is None:
                # 解析失败时也保存本轮用户输入到历史
                history.append({"role": "user", "content": description})
                history.append({"role": "assistant", "content": '{"error": "parse_failed"}'})
                save_history(history)
                print()
                continue

            commodity = validate_and_save(testcase)

            # 解析成功，保存本轮对话到历史
            history.append({"role": "user", "content": description})
            history.append({"role": "assistant", "content": json.dumps(commodity.model_dump(), ensure_ascii=False)})
            save_history(history)

            print(f"\n[OK] 测试用例已生成并保存（Pydantic 校验通过）:")
            print(json.dumps(commodity.model_dump(), ensure_ascii=False, indent=2))
            print()

        except ValidationError as e:
            history.append({"role": "user", "content": description})
            history.append({"role": "assistant", "content": json.dumps(testcase, ensure_ascii=False)})
            save_history(history)
            print(f"\n[解析失败] Pydantic 校验失败：{e}\n")
        except Exception as e:
            print(f"\n[解析失败] {e}\n")

if __name__ == "__main__":
    main()
