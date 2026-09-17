"""Home-screen navigation over simulated Windows/Chrome boundaries."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from Generalization.desktop import GeneralDesktop
from RoshElectroptics import rosh_thorlabs_tafnit as app


LABEL = "דרישה לרכש"
HOST = "tafnit.example.edu"


def window(handle, title):
    return SimpleNamespace(_hWnd=handle, title=title + " - Google Chrome", left=0,
                           activate=Mock(), maximize=Mock())


def page(*, request=None, status=None, host=HOST, dpr=1):
    return dict(host=host, dpr=dpr, request=request, status=status,
                form=request is not None and status is not None)


class StartupTests(unittest.TestCase):
    def setUp(self):
        self.home = window(1, "Tafnit")
        self.request = window(2, LABEL)
        self.windows = [self.home]
        self.pages = {1: page(), 2: page(request="", status="0")}
        self.p = Mock()
        self.p.getAllWindows.side_effect = lambda: self.windows
        self.p.size.return_value = (2560, 1440)
        self.clipboard = Mock()
        self.labels = {LABEL: ['[id="purchase"]']}
        self.clicked = []
        self.menu_steps = []
        self.config = SimpleNamespace(tafnit_host=HOST)

        def reader(win):
            result = Mock()
            result.read.side_effect = lambda expression: self.pages[win._hWnd]
            return result

        self.reader = Mock(side_effect=reader)
        for patcher in (
            patch.dict("sys.modules", {"pyautogui": self.p, "pyperclip": self.clipboard}),
            patch.object(app, "os", SimpleNamespace(name="nt")),
            patch.object(app, "ChromeReader", self.reader),
            patch.object(app.time, "sleep"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def install_navigation(self, *, popup=True):
        def click(selector):
            self.clicked.append(selector)
            if selector == '[id="purchase"]':
                if popup:
                    self.windows.append(self.request)
                else:
                    self.home.title = self.request.title
                    self.pages[1] = page(request="", status="0")

        for patcher in (
            patch.object(app.TafnitDesktop, "controls_with_text", side_effect=lambda label: self.labels.get(label, [])),
            patch.object(app.TafnitDesktop, "click_selector", side_effect=click),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def create(self, cls=app.TafnitDesktop, **kwargs):
        if cls is GeneralDesktop:
            return cls(Path("unused"), self.config, SimpleNamespace(), SimpleNamespace(), **kwargs)
        return cls(Path("unused"), self.config, **kwargs)

    def test_home_opens_exact_purchase_request_popup_for_both_adapters(self):
        self.install_navigation()
        for cls in (app.TafnitDesktop, GeneralDesktop):
            with self.subTest(adapter=cls.__name__):
                self.windows = [self.home]
                self.clicked.clear()
                ui = self.create(cls)
                self.assertEqual(ui.main._hWnd, 2)
                self.assertEqual(self.clicked, ['[id="purchase"]'])

    def test_home_can_open_request_in_same_window(self):
        self.install_navigation(popup=False)
        ui = self.create()
        self.assertEqual(ui.main._hWnd, 1)
        self.assertEqual(self.clicked, ['[id="purchase"]'])

    def test_existing_request_is_preferred_over_home_without_navigation(self):
        self.windows.append(self.request)
        ui = self.create()
        self.assertEqual(ui.main._hWnd, 2)
        self.p.click.assert_not_called()

    def test_home_opens_kalirkosh_menu_sequence_then_exact_request(self):
        self.install_navigation()
        self.labels[LABEL] = []
        def template(name, **kwargs):
            self.menu_steps.append((name, kwargs))
            if name == "klita":
                self.labels[LABEL] = ['[id="purchase"]']
        with patch.object(app.TafnitDesktop, "template", side_effect=template):
            ui = self.create()
        self.assertEqual(ui.main._hWnd, 2)
        self.assertEqual(self.menu_steps, [
            ("ivrit - main", {"relative_position": (.5, .3)}),
            ("yazam", {"relative_position": (-.5, .3)}),
            ("ivrit - secondary", {}), ("klita", {}),
        ])
        self.assertEqual(self.clicked, ['[id="purchase"]'])

    def test_missing_menu_template_stops_without_opening_request(self):
        self.install_navigation()
        self.labels[LABEL] = []
        with patch.object(app.TafnitDesktop, "template", side_effect=app.AutomationError("Missing menu template")):
            with self.assertRaisesRegex(app.AutomationError, "template"):
                self.create()
        self.assertEqual(self.clicked, [])

    def test_menu_without_exact_label_times_out_without_opening_request(self):
        self.install_navigation()
        self.labels[LABEL] = []
        with patch.object(app.TafnitDesktop, "template"), \
             patch.object(app.time, "monotonic", side_effect=range(0, 200, 5)):
            with self.assertRaisesRegex(app.AutomationError, "menu"):
                self.create()
        self.assertEqual(self.clicked, [])

    def test_resume_can_attach_to_existing_saved_request(self):
        self.windows.append(self.request)
        self.pages[2] = page(request="123", status="0")
        ui = self.create(allow_open_request=False)
        self.assertEqual(ui.main._hWnd, 2)
        self.p.click.assert_not_called()

    def test_single_chrome_with_institution_title_is_host_verified(self):
        self.install_navigation()
        self.home.title = "Example Institute - Google Chrome"
        self.assertEqual(self.create().main._hWnd, 2)

    def test_ambiguous_home_windows_are_rejected_before_reading(self):
        self.windows.append(window(3, "Tafnit"))
        with self.assertRaises(app.AutomationError):
            self.create()
        self.reader.assert_not_called()

    def test_resume_at_home_never_opens_another_request(self):
        self.install_navigation()
        for cls in (app.TafnitDesktop, GeneralDesktop):
            with self.subTest(adapter=cls.__name__):
                with self.assertRaisesRegex(app.AutomationError, "resume|Resume|original"):
                    self.create(cls, allow_open_request=False)
                self.assertEqual(self.clicked, [])

    def test_multiple_request_windows_are_rejected(self):
        self.windows += [self.request, window(3, LABEL)]
        with self.assertRaises(app.AutomationError):
            self.create()
        self.reader.assert_not_called()

    def test_wrong_host_or_scaling_stops_before_navigation(self):
        self.install_navigation()
        for info in (page(host="other.example"), page(dpr=1.25)):
            with self.subTest(info=info):
                self.pages[1] = info
                with self.assertRaises(app.AutomationError):
                    self.create()
                self.assertEqual(self.clicked, [])

    def test_ambiguous_exact_menu_labels_are_never_clicked(self):
        self.install_navigation()
        self.labels[LABEL] = ['[id="purchase"]', '[id="another"]']
        with self.assertRaisesRegex(app.AutomationError, "ambiguous|exactly one"):
            self.create()
        self.assertEqual(self.clicked, [])

    def test_new_window_must_be_on_configured_host_and_new_blank(self):
        self.install_navigation()
        for info in (page(request="123", status="0"), page(request="", status="1"),
                     page(request="", status="0", host="other.example")):
            with self.subTest(info=info):
                self.windows = [self.home]
                self.pages[2] = info
                self.clicked.clear()
                with self.assertRaises(app.AutomationError):
                    self.create()
                self.assertEqual(self.clicked, ['[id="purchase"]'])

    def test_popup_timeout_never_repeats_purchase_click(self):
        self.install_navigation()
        self.pages[2] = page()
        with patch.object(app.time, "monotonic", side_effect=range(0, 200, 5)):
            with self.assertRaisesRegex(app.AutomationError, "open|load|popup"):
                self.create()
        self.assertEqual(self.clicked, ['[id="purchase"]'])

    def test_about_blank_popup_is_waited_for_without_repeating_click(self):
        self.install_navigation()
        reads = []
        def info(ui):
            reads.append(ui.main._hWnd)
            if reads == [1]:
                return page()
            if reads == [1, 2]:
                return page(host="")
            return page(request="", status="0")
        with patch.object(app.TafnitDesktop, "page_info", autospec=True, side_effect=info):
            self.assertEqual(self.create().main._hWnd, 2)
        self.assertEqual(reads, [1, 2, 2])
        self.assertEqual(self.clicked, ['[id="purchase"]'])

    def test_multiple_new_windows_stop_without_picking_one(self):
        self.install_navigation()
        def click(selector):
            self.clicked.append(selector)
            self.windows.extend([self.request, window(3, LABEL)])
        with patch.object(app.TafnitDesktop, "click_selector", side_effect=click):
            with self.assertRaisesRegex(app.AutomationError, "Multiple"):
                self.create()
        self.assertEqual(self.clicked, ['[id="purchase"]'])

    def test_other_form_with_purchase_fields_is_rejected_after_open(self):
        self.install_navigation()
        self.request.title = "הזמנת רכש - Google Chrome"
        with self.assertRaisesRegex(app.AutomationError, "purchase request|דרישה לרכש"):
            self.create()

    def test_request_fields_in_unrelated_existing_window_are_rejected(self):
        self.home.title = "הזמנת רכש - Google Chrome"
        self.pages[1] = page(request="", status="0")
        with self.assertRaisesRegex(app.AutomationError, "purchase request|דרישה לרכש"):
            self.create()


class MenuLabelTests(unittest.TestCase):
    def choices(self, controls):
        ui = object.__new__(app.TafnitDesktop)
        ui.reader = SimpleNamespace(read=lambda expression: controls)
        return ui.controls_with_text(LABEL)

    def test_exact_hebrew_label_excludes_related_requests_and_orders(self):
        controls = [{"selector": str(i), "text": text} for i, text in enumerate([
            "דרישה למחסן", "הזמנת רכש", "דרישה לרכש שירות", "איתור דרישה לרכש",
            "Purchase request", "  \u200fדרישה\nלרכש\u200e  ",
        ])]
        self.assertEqual(self.choices(controls), ["5"])

    def test_nested_clickable_label_is_one_choice(self):
        controls = [{"selector": "html > body > div", "text": LABEL},
                    {"selector": "html > body > div > a", "text": LABEL}]
        self.assertEqual(self.choices(controls), ["html > body > div > a"])

    def test_separate_identical_labels_remain_ambiguous(self):
        controls = [{"selector": "a:nth-child(1)", "text": LABEL},
                    {"selector": "a:nth-child(2)", "text": LABEL}]
        self.assertEqual(len(self.choices(controls)), 2)


class RoshCliStartupTests(unittest.TestCase):
    def test_new_run_enables_opening_resume_disables_it_and_dry_run_skips_gui(self):
        from test_configuration import PROFILE
        from test_rosh_thorlabs_tafnit import QUOTE
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf = root / "quote.pdf"
            pdf.write_bytes(b"%PDF-synthetic")
            config = root / "config.local.json"
            config.write_text(json.dumps(PROFILE))
            args = [str(pdf), "--config", str(config), "--state-dir", str(root / "state")]
            with patch.object(app, "load_quote", return_value=app.parse_quote_text(QUOTE)), \
                 patch.object(app, "TafnitDesktop") as desktop, \
                 patch.object(app, "run_entry"), patch.object(app.time, "sleep"), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(app.main(args + ["--dry-run"]), 0)
                desktop.assert_not_called()
                self.assertEqual(app.main(args), 0)
                self.assertTrue(desktop.call_args.kwargs["allow_open_request"])
                self.assertEqual(app.main(args + ["--resume"]), 0)
                self.assertFalse(desktop.call_args.kwargs["allow_open_request"])


if __name__ == "__main__":
    unittest.main()
