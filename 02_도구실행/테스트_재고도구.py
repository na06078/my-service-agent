"""교재 모의 함수의 행동만 검사합니다. 실제 LLM 검증과 별개입니다."""
import importlib
import unittest


class InventoryToolTests(unittest.TestCase):
    def module(self):
        try:
            return importlib.import_module("inventory_tool")
        except ModuleNotFoundError:
            self.fail("inventory_tool 구현이 아직 없습니다.")

    def test_textbook_success_is_fixed_mock_quantity(self):
        result = self.module().get_inventory("A-17", "BUSAN-02")
        self.assertEqual(result, {
            "sku": "A-17", "warehouse_id": "BUSAN-02",
            "available_quantity": 7, "checked_at": "2026-08-27T01:55:00+09:00",
        })

    def test_unapproved_warehouse_returns_error(self):
        self.assertEqual(self.module().get_inventory("A-17", "BUSAN-03"),
                         {"error": "WAREHOUSE_NOT_ALLOWED"})

    def test_textbook_does_not_implement_sku_validation(self):
        self.assertEqual(self.module().get_inventory("", "BUSAN-02")["available_quantity"], 7)

    def test_followup_preserves_user_query_and_tool_call_id(self):
        from langchain_core.messages import AIMessage
        first = AIMessage(content="", tool_calls=[{
            "name": "get_inventory", "args": {"sku": "A-17", "warehouse_id": "BUSAN-02"},
            "id": "call-test", "type": "tool_call",
        }])
        messages = self.module().build_followup_messages("원래 질문", first, {"available_quantity": 7})
        self.assertEqual([message.type for message in messages], ["human", "ai", "tool"])
        self.assertEqual(messages[0].content, "원래 질문")
        self.assertEqual(messages[2].tool_call_id, "call-test")


if __name__ == "__main__":
    unittest.main(verbosity=2)
