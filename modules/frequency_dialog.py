"""The question asked when a selection of recordings mixes sample rates.

Processing can take any mix ("Process all"). A dataset can't: its rows are
fed to one model, whose input is a fixed number of samples, so a dataset is
built from one rate.

Both functions take `rates` ({stem: rate in Hz}) and return the stems to carry
on with, or None if the user cancelled. A selection at one rate isn't asked
about.
"""
from collections import Counter

from PySide6.QtWidgets import QMessageBox

TITLE = "Mixed frequencies"


def rate_text(rate) -> str:
    return f"{float(rate):g} Hz"


def _summary(rates) -> str:
    counts = Counter(rates.values())
    return "\n".join(f"    {rate_text(rate)}: {counts[rate]} recording(s)"
                     for rate in sorted(counts))


def _ask(parent, text, options):
    """A message box with one button per (label, value) in `options`, plus
    Cancel. The chosen value, or None. Tests replace this."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(TITLE)
    box.setText(text)
    buttons = {box.addButton(label, QMessageBox.ButtonRole.AcceptRole): value
               for label, value in options}
    box.addButton(QMessageBox.StandardButton.Cancel)
    box.exec()
    return buttons.get(box.clickedButton())


def _only(rates, rate):
    return {stem for stem, r in rates.items() if r == rate}


def choose_for_processing(parent, rates):
    """Process all, or the recordings at one rate."""
    if len(set(rates.values())) <= 1:
        return set(rates)
    choice = _ask(
        parent,
        "The selected recordings were made at different frequencies:\n\n"
        f"{_summary(rates)}\n\n"
        "They can all be processed, but each frequency needs its own "
        "dataset and its own model.",
        [("Process all", "all")]
        + [(f"Process {rate_text(r)} only", r) for r in sorted(set(rates.values()))])
    if choice is None:
        return None
    return set(rates) if choice == "all" else _only(rates, choice)


def choose_for_dataset(parent, rates):
    """The recordings at one rate - a dataset can't hold more than one."""
    if len(set(rates.values())) <= 1:
        return set(rates)
    choice = _ask(
        parent,
        "These recordings were made at different frequencies:\n\n"
        f"{_summary(rates)}\n\n"
        "A dataset can only hold one frequency. Which should this one use?",
        [(f"Use {rate_text(r)} only", r) for r in sorted(set(rates.values()))])
    return None if choice is None else _only(rates, choice)
