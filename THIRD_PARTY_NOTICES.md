# Bundled source and assets

`RoshElectroptics/_vendor/general_gui_controller.py` and the ten PNG crops in
`RoshElectroptics/templates/` come from the existing
[general-gui-controller project](https://github.com/mkali-personal/general-gui-controller).
The controller is included to preserve its image matching behavior without
requiring a second local checkout. The application uses the template detector;
unrelated optional helpers are not invoked.

The home-screen menu sequence and the `ivrit - main`, `yazam`,
`ivrit - secondary`, and `klita` crops are reused from that project's
`kalirkosh.py` workflow and `ggc-templates` directory.

The crops show generic controls from the Tafnit interface. They contain no
filled form values or identifying browser chrome. Product names and interface
assets remain associated with their respective owners.

Python dependencies are listed in `pyproject.toml` and pinned in `uv.lock`;
their own licenses apply. This repository does not relicense third-party
source or assets.
