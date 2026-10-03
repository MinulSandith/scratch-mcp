# Test fixture

`sample.sb3` is a small Scratch 3 project (Stage + sprites "Cat" and "Ball") with
variables, a list, a broadcast, if/else, a custom block, menus and the pen extension.

How it was made:

1. `python tests/fixtures/make_sample.py OUT_DIR` builds it with scratch-mcp.
2. The result was loaded into scratch-vm (Node.js) and saved again with
   `vm.saveProjectSb3()`, so the committed file is serialized by Scratch's own code.
