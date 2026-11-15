import json
import unittest
from pathlib import Path
from hogwarts_voice.voice_presets import (
    STYLE_ORIGINAL, STYLE_ROSMEN, DEFAULT_STYLE, ROSMEN_READINGS,
    visible_name, spoken_aliases, validate_style,
)
from hogwarts_voice.game_commands import to_game_command, SUPPORTED_BASE_COMMANDS
from hogwarts_voice.game_interactions import ACTION_IDS
from hogwarts_voice.ru_asr import load_spell_aliases, match_incantation

class BookVoiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.book = load_spell_aliases()
        cls.allowed = list(cls.book)

    def test_complete_book_style(self):
        self.assertEqual(set(ROSMEN_READINGS), set(self.book))
        self.assertEqual(DEFAULT_STYLE, STYLE_ROSMEN)

    def test_book_spell_routing(self):
        cases = {
            "остолбеней": "Stupefy",
            "вспыхни": "Confringo",
            "вингардиум левиоса": "Wingardium",
            "экспелярмус": "Expelliarmus",
            "империо": "Imperius",
            "авада кедавра": "AvadaKedavra",
            "покажи путь": "AppareVestigium",
            "древняя магия": "Finisher",
            "трансформация": "Transformation",
            "люмос": "Lumos",
        }
        for spoken, expected in cases.items():
            with self.subTest(spoken=spoken):
                selected, reason = match_incantation(
                    spoken, self.book, enabled=self.allowed, style=STYLE_ROSMEN)
                self.assertEqual(selected, expected, reason)

    def test_styles_are_actually_different(self):
        for spoken in ("остолбеней", "вспыхни", "покажи путь", "древняя магия"):
            self.assertIsNone(match_incantation(
                spoken, self.book, enabled=self.allowed, style=STYLE_ORIGINAL)[0])
        self.assertEqual(visible_name("Stupefy", STYLE_ROSMEN), "Остолбеней")
        self.assertEqual(visible_name("Stupefy", STYLE_ORIGINAL), "Ступефай")

    def test_words_are_not_misrouted(self):
        for spoken in ("невидимость", "к цели", "левиоза", "вингардиум",
                       "остолбенеть", "заклинание", "привет"):
            with self.subTest(spoken=spoken):
                self.assertIsNone(match_incantation(
                    spoken, self.book, enabled=self.allowed, style=STYLE_ROSMEN)[0])

    def test_permission_remains_effective(self):
        self.assertIsNone(match_incantation(
            "остолбеней", self.book, enabled=["Lumos"], style=STYLE_ROSMEN)[0])

    def test_bad_style_fails(self):
        with self.assertRaises(ValueError):
            validate_style("magic")
        with self.assertRaises(ValueError):
            match_incantation("остолбеней", self.book,
                              enabled=self.allowed, style="magic")

    def test_every_spoken_command_maps_to_known_game_command(self):
        for spell in self.book:
            if spell in ACTION_IDS:
                continue
            with self.subTest(spell=spell):
                ipc = to_game_command(spell)
                self.assertIn(ipc, SUPPORTED_BASE_COMMANDS)
                self.assertLessEqual(len(ipc.encode("ascii")), 27)
        self.assertEqual(to_game_command("Stupefy"), "Stupefy")
        self.assertEqual(to_game_command("Imperius"), "Imperio")
        self.assertEqual(to_game_command("Disillusionment"), "Invisica")
        self.assertEqual(to_game_command("Wingardium"), "WingardiumLeviosa")
        self.assertEqual(to_game_command("Transformation"), "TransfiguraVerto")
        self.assertEqual(to_game_command("Finisher"), "Smash")

    def test_new_context_and_menu_actions(self):
        expected = {
            "алохомора": "Alohomora",
            "фините": "Finite",
            "акцио метла": "Broomstick",
            "открой карту": "Map",
            "открой инвентарь": "Inventory",
        }
        for spoken, spell in expected.items():
            with self.subTest(spoken=spoken):
                selected, _ = match_incantation(
                    spoken, self.book, enabled=self.allowed, style=STYLE_ROSMEN
                )
                self.assertEqual(selected, spell)
        self.assertEqual(to_game_command("Broomstick"), "AccioBroomstick")
        self.assertEqual(to_game_command("Map"), "AppertaMappa")
        self.assertEqual(to_game_command("Inventory"), "AppertaCodex")
        self.assertEqual(to_game_command("Finite"), "Finite")
        for phrase, spell, game_command in [
            ("петрификус тоталус", "Petrificus", "StealthTakedown"),
            ("конжурация", "Conjuration", "Conjuration"),
            ("призови гиппогрифа", "Mount", "AccioMount"),
            ("открой задания", "Quests", "AppertaQuaestiones"),
            ("открой персонажа", "Character", "AppertaMeritas"),
            ("открой таланты", "Talents", "AppertaFalcultates"),
            ("открой коллекции", "Collections", "AppertaCompendium"),
            ("открой испытания", "Challenges", "AppertaIncantatem"),
            ("открой письма", "Mail", "AppertaLiterae"),
            ("открой настройки", "Settings", "AppertaConfiguratio"),
        ]:
            with self.subTest(phrase=phrase):
                chosen, _ = match_incantation(
                    phrase,self.book,enabled=self.allowed,style=STYLE_ROSMEN
                )
                self.assertEqual(chosen,spell)
                self.assertEqual(to_game_command(chosen),game_command)
        with self.assertRaises(ValueError):
            to_game_command("Alohomora")
        for phrase in ("открой карты", "алохомору", "акцио метлы"):
            self.assertIsNone(match_incantation(
                phrase, self.book, enabled=self.allowed, style=STYLE_ROSMEN)[0])

    def test_unknown_game_command_is_blocked(self):
        with self.assertRaises(ValueError):
            to_game_command("UnknownSpell")

if __name__ == "__main__":
    unittest.main()
