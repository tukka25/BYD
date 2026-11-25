from evaluate import prompt_ids


class FakeTokenizer:
    def __init__(self, result=None):
        self.calls = []
        self.result = [1, 2, 3] if result is None else result

    def apply_chat_template(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return self.result


ROW = {"system": "draw charts", "prompt": "bar of sales"}


def test_thinking_left_on_builds_the_prompt_every_earlier_run_built():
    tokenizer = FakeTokenizer()
    assert prompt_ids(tokenizer, ROW) == [1, 2, 3]
    messages, kwargs = tokenizer.calls[0]
    assert messages == [{"role": "system", "content": "draw charts"}, {"role": "user", "content": "bar of sales"}]
    assert kwargs == {"tokenize": True, "add_generation_prompt": True}


def test_thinking_off_asks_the_template_to_close_the_think_block():
    tokenizer = FakeTokenizer()
    prompt_ids(tokenizer, ROW, thinking=False)
    assert tokenizer.calls[0][1]["enable_thinking"] is False


def test_dict_and_batched_token_ids_come_back_flat():
    assert prompt_ids(FakeTokenizer({"input_ids": [4, 5]}), ROW) == [4, 5]
    assert prompt_ids(FakeTokenizer([[6, 7]]), ROW) == [6, 7]
