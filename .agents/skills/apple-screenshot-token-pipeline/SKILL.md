---
name: apple-screenshot-token-pipeline
description: Pipeline for reverse-engineering iOS native screenshots into pixel-accurate Apple Design Tokens. Includes physical measurement helper and schema validation.
---

# Apple Screenshot Token Pipeline

A specialized skill for extracting pixel-accurate Apple Design Tokens from paired iOS screenshots (Light and Dark mode) using a hybrid approach of physical OpenCV measurement and multimodal semantic vision.

## Pipeline Tools & Resources

- `measure_helper.py`: Local Python measurement probe for physical pixel metrics, color sampling, and dual-track corner curvature fitting (traditional circle + superellipse).
- `validate_pair.py`: Automated validation script verifying syntax, data contracts, symmetry, and ground-truth alignment.
- `design_token_schema.json`: Formal data contract schema defining the extracted token structure.

## Sequential Execution Workflow (Strict Protocol)

> [!IMPORTANT]
> **Mandatory Execution Rules**:
>
> 1. **Sequential Mode**: Do NOT analyze both images simultaneously. Light mode MUST be completed and verified first before touching Dark mode.
> 2. **File Naming Standard**:
>    - Images: `{folder_name}_light.<ext>` and `{folder_name}_dark.<ext>` (supports png, jpg, jpeg, webp)
>    - JSON: `{folder_name}_light.json` and `{folder_name}_dark.json`
> 3. **No Premature Aggregation**: Do NOT aggregate across folders or generate the final design system without explicit user instructions.
> 4. **No Extraneous Documentation**: Do NOT create `implementation-notes.md` or any non-standard markdown notes. Only the 5 standard files are permitted.
> 5. **Dual-Track Radius**: Always lock geometry using both traditional nominal radius (`traditional_card_radius_pt`) and superellipse curvature (`shape_exponent_n` + formula).

1. **Verify & Measure**:
   - Ensure `{folder_name}_light.<ext>` and `{folder_name}_dark.<ext>` exist in the target folder.
   - Run the physical probe:

     ```bash
     python .agents/skills/apple-screenshot-token-pipeline/measure_helper.py <folder_path>
     # 可选：生成梯度法向彩虹伪彩图与 CLAHE 增强图，辅助多模态视觉审视微光边缘
     # python .agents/skills/apple-screenshot-token-pipeline/measure_helper.py <folder_path> --visualize
     ```

   - Read `raw_measurements.json` for baseline ground truth (margins, gaps, traditional radius, superellipse formula).

2. **Phase 1: Light Mode Baseline (浅色基准与初验)**:
   - Focus exclusively on `{folder_name}_light.<ext>` + `light_mode_samples`.
   - Lock the geometric curvature using the dual-track fitting engine (traditional radius + superellipse $n$ and formula).
   - Lock 8pt spacing rhythm (decoupling component padding vs optical insets) and SF Pro typography scale.
   - Extract light semantic background and surface levels.
   - Write `{folder_name}_light.json`.
   - **Validate Light Mode**:

     ```bash
     python .agents/skills/apple-screenshot-token-pipeline/validate_pair.py <folder_path> --mode light
     ```

   - Must pass with exit code 0 before proceeding to Phase 2.

3. **Phase 2: Dark Mode Mapping (深色映射与继承)**:
   - Inherit `geometry`, `spacing`, and `typography` directly from `{folder_name}_light.json` to guarantee mathematical symmetry.
   - Inspect `{folder_name}_dark.<ext>` + `dark_mode_samples` for elevation greys, 0.5px hairlines, and accent tints.
   - Write `{folder_name}_dark.json`.

4. **Phase 3: Final Pair Validation (双模终验)**:
   - Run full pair symmetry and schema validation:

     ```bash
     python .agents/skills/apple-screenshot-token-pipeline/validate_pair.py <folder_path>
     ```

   - Must pass with exit code 0 to complete the session.
   - **Stop and report**. Await the user's explicit command for any next action.
