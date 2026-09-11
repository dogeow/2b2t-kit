# Voyager attribution

Parts of the SkillManager structure in `kit_skills/library.py` are adapted from:

- MineDojo/Voyager, `voyager/agents/skill.py`
- Commit `55e45a880755d0c8c66ca7fb5fe7962ac8974f89`
- Copyright (c) 2023 MineDojo Team
- MIT License: full text in `kit_skills/vendor/voyager/LICENSE`

The port keeps the bounded skill-retrieval and versioned code/description-storage workflow. It replaces LangChain/OpenAI/Chroma dependencies with local SQLite and lexical retrieval; uses declarative Kit programs; and adds native evidence, candidate verification, and non-mutating observation. The original source is retained as reference text and is not imported or executed. `SOURCE.json` records the exact URLs and checksums.

No pretrained model or model weights are bundled. This package is not the original Voyager runtime and makes no claim of reproducing its benchmark results.
