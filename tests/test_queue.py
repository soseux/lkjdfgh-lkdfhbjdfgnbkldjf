from dota_predictor.workers.queue import retry_delay_seconds


def test_retry_delay_is_exponential_and_capped() -> None:
    assert retry_delay_seconds(1) == 5
    assert retry_delay_seconds(2) == 10
    assert retry_delay_seconds(3) == 20
    assert retry_delay_seconds(99) == 3600
