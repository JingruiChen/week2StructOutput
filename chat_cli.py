import json
import os
import anthropic
from pydantic import ValidationError
from schemas import Commodity


client = anthropic.Anthropic(
    api_key="or_4170110cb92fd356eca9b2fe0d4b0912e9cbea4e294324b9a612c523c569a6e7",
    base_url="https://b.onerouter.com/api",
)

HISTORY_FILE = "chat_history.json"


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
    system_prompt = """你是一个严格的商品信息提取器。

【处理规则】
第一步：判断输入是否有效
- 如果输入是乱码、无意义字符、与商品完全无关的内容（如天气、诗歌、问候语等），直接输出：{"error": "parse_failed"}

第二步：提取商品字段（仅当输入有效时执行）
- 只能提取描述中明确给出的信息，绝对禁止猜测、推断或自行编造任何字段值
- 用户可能分多轮补充信息，请结合历史对话中已提供的字段
- 必须同时包含全部 4 个字段才算成功：
  - id: int（商品编号）
  - name: str（商品名称）
  - price: float（商品价格）
  - stock: int（商品库存）
- 任何一个字段在描述中没有明确给出，输出：{"error": "parse_failed"}
- 不判断字段值是否合法，原样提取即可

第三步：输出结果
- 成功时只输出 JSON，不包含任何其他文字
- 失败时输出：{"error": "parse_failed"}"""

    # 在历史记录基础上追加当前输入
    messages = history + [{"role": "user", "content": description}]

    for attempt in range(1, max_retries + 1):
        try:
            response = client.messages.create(
                model="claude-opus-4-6",
                max_tokens=512,
                system=system_prompt,
                messages=messages,
            )
            content = response.content[0].text
            json_str = extract_json(content)
            parsed = json.loads(json_str)

            if parsed.get("error") == "parse_failed":
                raise ValueError("parse_failed")

            return parsed

        except Exception:
            if attempt < max_retries:
                print(f"  [解析失败] 第 {attempt} 次，正在重试...")
            else:
                print(f"  [解析失败] 已尝试 {max_retries} 次，解析失败，返回主页面。")
                return None

    return None


def validate_and_save(testcase: dict, filename: str = "testcases.json") -> Commodity:
    """用 Pydantic 校验测试用例并追加保存到 JSON 文件"""
    commodity = Commodity(**testcase)

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
    print("=== Claude 商品测试用例生成器 ===")
    print("输入商品描述，将生成符合 Pydantic schema 的 JSON 测试用例")
    print("输入 'history' 查看历史对话  |  输入 'clear' 清除历史  |  输入 'quit' 退出\n")

    # 启动时加载历史记录
    history = load_history()
    if history:
        print(f"[已加载 {len(history) // 2} 轮历史对话]\n")

    while True:
        description = input("请输入商品描述: ").strip()

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
