# Tartous Hospital – Sheet 165: Section A-A and detail sections (redraw)

Source: a phone photo (PDF) of the 1982 original. Project 452, Tartous Hospital, drawing no. 165, dated 1982/09/15.

## Files
| File | What it is |
|---|---|
| `tartous_402_section_AA_details.dxf` | The CAD drawing (AutoCAD 2018 DXF). Open it in AutoCAD and use **SAVEAS → DWG**. |
| `preview_sheet_165.pdf` / `.png` | A plot preview of the paper-space sheet. |
| `build_dxf.py` | The script that generates the DXF (`pip install ezdxf`, then `python build_dxf.py`). |
| `render_preview.py` | Plots the sheet at true A1 size with real line weights (`python render_preview.py file.dxf out.pdf 150`). |

## Drawing set-up
- **Model space is 1:1 in centimetres** (`INSUNITS` = cm), because every dimension on the original is in cm.
- In Section A-A and Detail B, the model Y coordinate equals the real level. For example, the 2nd floor finish is at Y = 1605.
- In Section A-A, X = 0 is grid 6.
- **Layout `SHEET-165`** is an A1 sheet laid out like the original:

  | Drawing | Viewport scale |
  |---|---|
  | Section A-A | 1:100 |
  | Detail B | 1:50 |
  | Plans 1.1, 2.2 and 3.3 | 1:50 |
  | Section C-C | 1:10 |
  | Facade groove plan detail | 1:10 |

  The title block is redrawn in paper space.
- **Dimension styles:**
  - `DIM-100`, `DIM-50` and `DIM-10` give 2 mm text on paper at each scale.
  - Architectural ticks.
- **Layers:**
  - `A-*` follows AIA-style naming. Cut elements are poché-filled on `A-POCHE`.
  - **`Z-INFERRED` (magenta) marks everything that was scaled from the photo or inferred rather than read as a written number.**

## How the scan distortion was removed
- The photo was perspective-corrected using the four corners of the sheet border.
- The correction was checked against written dimensions in both directions:
  - The 20 cm and 80 cm dimensions in the 1:10 groove detail measure to within 1 %.
  - The 1170 cm facade chain in Section A-A also checks out.
- **All geometry is built from the written numbers.** Lines were not traced from the photo, so skew, wobble and fold distortion do not carry into the drawing.

## Written values used (all checked for consistency)
**Floor levels (cm):**
- Basement: +195 F and +545 F
- Ground: +885 F
- 1st floor: +1255 F
- 2nd floor: +1605 F
- Roof: +1943 B, parapet top +2055
- Stair core: +2275 B, top +2387

**Stair half-landings:** +370, +715, +1070, +1430 and +1780. Each is the midpoint between two floor levels; the +1780 landing sits 6 cm above that midpoint, as written.

**Floor build-up:** 12 finish + 38 ribbed (hollow-block) slab = 50. The roof slab is 38. Basement slabs are 20.

**Facade height chain:** 90 / 230 / 50 / 90 / 155 / 10 / 35 / 60 / 90 / 155 / 55 / 150. This totals 1170, which matches 2055 − 885. The same chain appears in Detail B.

**Corridor chain:** 38 / 50 / 10 / 240 / 50 / 50 / 10 / 240 / 50 / 320 / 20 / 320 / 20 / 330. This gives a 240 cm clear height to the suspended ceiling, with a 10 cm ceiling and a 50 cm void.

**Section C-C:**
- Parapet wall 15 + 2 + 2 render
- Coping 30 wide, 15 thick
- Parapet height 112 above the roof slab
- 20 cm projection outside the parapet face

**Groove detail:** groove 20 wide × 20 deep. Below it are steps of 15 + 15, and the overall width is 80.

**Plans:**
- Plan 3.3: 120 + 30 = 150 from grid 6.
- Plan 1.1: 10/20/10, 220/20/220, 30/25/10/10/60, 20/15/45, column 25, wall 15.

## Line weights (plot at 1:1 on A1)
Cut walls and slabs 0.30 mm, stairs 0.25, floor finishes and ground 0.13, elevation/beyond lines, glazing, dims and grids 0.09. Cut walls and slabs are poché-filled (dark), as on the original. The thin double lines at grids 4 and 3 are 12 cm partitions, not solid columns, as drawn on the original.

## Inferred or scaled items (please verify)
1. **Grid spacing in Section A-A.** No horizontal dimensions are written, so the spacing was scaled from the corrected photo: 6→5 = 465, 5→4 = 390, 4→3 = 570, 3→2 = 365, 2→1 = 480 (±10 cm). These are shown as magenta dimensions.
2. **Stair geometry.** Counted on the original: 10 risers per flight and 9 treads of 30 cm (270 cm run). The rise per step comes from the written landing levels. Landing widths (≈160 cm) and the 15 cm floor plates and landings were scaled.
3. **Doors, windows, partitions and columns seen beyond the cut** were placed by scaling (±5 cm). Doors are 210 high, 90 wide in the core. The high windows run from +82 to +238 above floor, with the transom at +125.
4. **Ground-floor glazing set-back.** It is about 175 cm from the facade face in Section A-A and 188 cm in Detail B, both scaled.
5. **Roof overhang.** About 105 cm from the facade face in both Section A-A and Detail B (scaled; these agree). Plan 3.3 writes 120 + 30 = 150 measured from grid 6.
6. **Section C-C layer names.** The original has 7 Arabic labels, but none can be read in the photo, even at 4× zoom. Typical names are shown instead. The thicknesses are the written ones: 8 / 2 / 2 / 4, with slab 38.
7. **Section C-C parapet wall.** The written thickness is partly legible: "13" is read. It also measures 14 cm on the photo.
8. **Plans 1.1 and 2.2.** These are partly dimensioned. Where no number is written, positions were scaled.
9. **Title block.** The department line reads "القسم الطبي (?)", which is uncertain. Signatures and names were left blank on purpose.

## Corrections after the side-by-side check against the original
- **Stairs:** the cut flights were upside down (steps under the waist). They are now drawn with the steps on top, plus a finish line, handrail pair, mid-rail, posts and end caps. The far flights show only their rails, hidden behind the near flight, as on the original.
- **Slabs:** blocks are every 54–57 cm (not 33). The slabs have solid beam zones at three places and a plain corridor band, as drawn.
- **Columns at grids 4 and 3:** 15 cm, filled. The ground-floor column sits left of grid 3, as drawn.
- **Canopy:** 58 cm (as Detail B), not 112. The facade and parapet positions were re-measured.
- **Detail B:** the facade face had been misread by about 65 cm, which shortened the roof overhang. It is re-drawn using the written 5 / 20 / 55 and 20 / 60, with blocks 38 @ 57.
- **Section C-C:** re-drawn from the written 2 / 2 / 13 / 2 coping, the 13 wall, the recess for the 34 upturn, and the 8 / 2 / 2 / 4 build-up.
- **Plans 1.1 and 2.2:** the panel runs 240–500 (20 + 220 + 20). The wall is hatched and the column cross-hatched, as on the original. All plan viewports are now placed exactly as on the sheet.
- **Basement:** dotted waterproofing on the outer wall faces. The earth hatch that isn't on the original has been removed.

## Notes
- Arabic text uses Arial. If it shows reversed or disconnected in an older AutoCAD, edit it with MTEXT, which shapes Arabic correctly in recent versions.
- A DWG converter couldn't be run in the build environment, which is why the deliverable is DXF. AutoCAD opens it with no loss; use SAVEAS → DWG 2018.
