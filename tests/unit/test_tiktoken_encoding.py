from chatbot.adapters.outbound.tiktoken_encoding import TiktokenEncoding


def test_tiktoken_encoding_round_trip() -> None:
    encoding = TiktokenEncoding()

    tokens = encoding.encode("saúde mental")

    assert encoding.decode(tokens) == "saúde mental"
