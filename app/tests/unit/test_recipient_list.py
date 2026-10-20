"""Тесты разбора списка получателей с именами (обращение {{name}})."""

from __future__ import annotations

import pytest

from cbmail.domain import recipient_list as rl


class TestSplitNamed:
    def test_angle_bracket_format(self) -> None:
        pairs, invalid = rl.split_named("Иван Петров <ivan@mail.ru>")
        assert pairs == [("ivan@mail.ru", "Иван Петров")]
        assert invalid == []

    def test_comma_name_format(self) -> None:
        pairs, _ = rl.split_named("petr@mail.ru, Пётр")
        assert pairs == [("petr@mail.ru", "Пётр")]

    def test_address_without_name(self) -> None:
        pairs, _ = rl.split_named("anna@mail.ru")
        assert pairs == [("anna@mail.ru", "")]

    @pytest.mark.regression
    def test_legacy_comma_separated_line_is_not_broken(self) -> None:
        """Старый ввод «адреса через запятую в одну строку» должен работать.

        Такую строку нельзя трактовать как «адрес + имя»: имени там нет, а
        второй адрес — полноценный получатель, а не часть обращения.
        """
        pairs, _ = rl.split_named("a@x.ru, b@y.ru, c@z.ru")
        assert pairs == [("a@x.ru", ""), ("b@y.ru", ""), ("c@z.ru", "")]

    def test_dedup_keeps_first_name(self) -> None:
        pairs, _ = rl.split_named("ivan@mail.ru, Иван\nIVAN@mail.ru, Другой")
        assert pairs == [("ivan@mail.ru", "Иван")]

    def test_line_without_email_is_invalid(self) -> None:
        pairs, invalid = rl.split_named("Просто имя без адреса\nok@mail.ru")
        assert pairs == [("ok@mail.ru", "")]
        assert invalid == ["Просто имя без адреса"]

    def test_empty(self) -> None:
        assert rl.split_named("") == ([], [])
        assert rl.split_named(None) == ([], [])


class TestNameMap:
    def test_only_named_addresses_present(self) -> None:
        mapping = rl.name_map("ivan@mail.ru, Иван\nanna@mail.ru")
        assert mapping == {"ivan@mail.ru": "Иван"}

    def test_normalized_keys(self) -> None:
        mapping = rl.name_map("Ivan@Mail.RU, Иван")
        assert mapping == {"ivan@mail.ru": "Иван"}


class TestFormatAndMerge:
    def test_round_trip(self) -> None:
        text = rl.format_lines([("ivan@mail.ru", "Иван"), ("a@x.ru", "")])
        assert text == "ivan@mail.ru, Иван\na@x.ru"
        # То, что сохранили, снова разбирается в те же пары.
        assert rl.split_named(text)[0] == [("ivan@mail.ru", "Иван"), ("a@x.ru", "")]

    def test_merge_prefers_primary_name(self) -> None:
        primary = [("ivan@mail.ru", "Иван")]
        extra = [("ivan@mail.ru", "Из файла"), ("new@x.ru", "Новый")]
        assert rl.merge_pairs(primary, extra) == [
            ("ivan@mail.ru", "Иван"),
            ("new@x.ru", "Новый"),
        ]

    def test_emails_only(self) -> None:
        assert rl.emails_only([("a@x.ru", "A"), ("b@y.ru", "")]) == ["a@x.ru", "b@y.ru"]
