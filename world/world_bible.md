# World Bible — *Badlands* (demo biome)

**Status:** 🟢 Creative core locked; visual language set. **Date:** 2026-06-10.
**Scope:** the demo's one cohesive biome — the **badlands start-zone** of a larger world.
**Companion:** the engine-facing elevation requirements live in the engine repo at
`docs/handoff/multi-level-terrain/BRIEF.md`. This bible is the creative half.

## Locked decisions (the calls this bible rests on)

- **Biome:** sun-scorched **badlands**, the *start* of a larger world (not a standalone arena).
- **Demo scope:** areas **A0–A5** (spine + exploration), one cohesive badlands kit. See `areas/` (gated).
- **Elevation:** **walkable tactical height-tiers** — built *first*; the demo waits on the engine.
- **Look rule (hard):** ONE cohesive baked look — every asset is a 3D model baked through the locked
  `game_iso_v1` iso pipeline (2:1 dimetric, az 45° / el 30°, 1 m = 64×32 px). **No painted backdrops.**

## 1. Setting

A cracked-clay basin at the harsh edge of a kingdom — the **first wild place** a player steps into,
ringed by impassable mesa walls and watched over, far to the north, by a fortress that does not want
visitors. It was lived in once: old waystones, a dry river, the bones of caravans that didn't make it.
Now it's raider country. The badlands are the demo's whole world, but they're built to feel like the
**doorway to somewhere much larger** — the selling point is **exploring the unknown**, and the badlands
should make you want to see what's past the ridge.

## 2. Tone

Harsh, sun-bleached, and a little lonely — but with stark beauty that **rewards looking closer**: an
alkali pool that's the only colour for miles, a lone monument, a story written in wreckage. Danger is
legible and earned, not cheap. Quiet, then sudden.

## 3. The larger world (context the demo lives inside)

The badlands are the **south-west** of the map. The player's anchor is the **safe City** (hub, centre);
the **green** lands (forest / swamp / rocky, south-east) are the next exploration frontier; the
**mountains + fortress + the Evil King** (north) are the high-level endgame you're *warned away* from
early. The demo previews this larger world — a distant fortress silhouette, the **Warning Ridge** (A5) —
without building it.

## 4. Visual language

### Silhouette rules
- **Legible elevation above all.** A player must read a tier's height **at a glance** — cool, deeply
  shadowed **cliff-faces** against warm, lit **tops**. Tactical clarity beats realism; this is the #1 art
  risk (see look pillar 1).
- **Silhouette-first, unlit-friendly.** The renderer is **2D unlit** — no live lighting, shaders, or
  particles. Forms must read by **big, chunky shape**, not surface detail. Cool **rock** vs. warm
  **ground** carries the contrast.
- **Props read as silhouettes.** A boulder, a tent, a waystone — recognizable from outline alone.
- **Cohesion over variety.** One palette, one chunkiness, one sun-direction baked into every asset.

### Palette (swatches — the badlands canvas)
| Role | Swatches |
|---|---|
| Ground (cracked clay / dust) | `#E4D2A8` bone · `#C8A26B` ochre · `#B5764A` baked terracotta |
| Rock / mesa (cool counter) | `#7A6E73` dust-mauve · `#5B6470` shadow blue-grey · `#3A3A42` basalt |
| Cliff-face / deep shadow | `#2E2A2E` (the tier-separation tone — used hard for elevation reads) |
| Vegetation (sparse, dead) | `#8A8B5A` sage · `#6E6244` dry brush |
| Water (alkali pool) | `#6FA89C` pale jade — slightly sickly, *not* inviting |
| Ambient / horizon (the canvas) | `#D8C9A8` hazy warm |
| Story / faction accents | `#A8431E` rust · `#922D2D` faded crimson · `#9C7A3C` weathered bronze |

### Scale references (anchored to the locked frame)
- **1 tile = 1 m = 64×32 px.** A human ≈ **1.8 m**.
- **Tier height ≈ 2.0 m** — a cliff you *can't* walk up (engine number: see the BRIEF, §6). Tiers must
  read as one clear step of separation.
- **Cover boulders ≈ 1.2–1.8 m** (chest-to-head — real cover for the directional shield).
- A **mesa** ≈ 2–3 tiers; the **Warning Ridge** reads as a wall, far taller.

## 5. Look pillars

1. **Legible elevation.** You always know how high you are and what's above you. Cool shadowed faces,
   warm tops, hard tier-separation tone. If the tiers don't read instantly, the look has failed.
2. **Silhouette-first, unlit-friendly.** Big readable shapes carry everything; no leaning on light,
   shaders, or particles.
3. **A world that was lived in.** The badlands *tell their story* — ruins, bones, abandoned camps,
   waystones. Environmental storytelling is the engine of "explore the unknown."
4. **One cohesive baked look.** Every asset is a 3D model through the *same* iso pipeline as the
   characters. Consistency is the brand.
5. **Harsh, but beautiful.** Scarcity and danger, punctuated by stark, memorable sights that pay off
   curiosity.
6. **Engineered uncertainty.** Elevation, LOS, and fog conspire to **deny sightlines** — a threat can
   close from just past where vision ends, and cresting a **blind ledge** should make you tense. Tension
   is a level-design *tool*, not an accident. This is a **critical world-building seam**, not merely an
   engine feature — it's the core reason walkable multi-level was chosen first.

## 6. "Alive" and "explore the unknown" (how the world breathes)

- **Ambient life** is delivered by **roaming entities** (critters, an NPC, the raider band) — these are
  **character-contract** assets (Model Producer's lane). The World-Builder **places the spawns and writes
  the encounters**, and briefs the **environment** around them (camp, ruins, props), not the creatures.
- **Density over completion:** there is **more to find than any player will see** — hidden stashes, a side
  path, a story-told-in-wreckage off the main line. Many will skip it and stumble into it later. That's
  the point.
- **The unknown is staged, not faked:** the Warning Ridge (A5) and the distant fortress make the larger
  world *visible and forbidden* without building it.

## 7. Asset language (recipes come next)

Every environment asset is one of: a **ground tile** (terrain class, per-cell height — gated on the
elevation bake contract), a **blocking feature** (mesa / cliff-face / boulder / wall — static collider +
occluder sprite), **water** (impassable sight-blocking band), or a **prop** (static, decorative or
small-blocking). The per-kind "how we make it" recipes are written once and approved in `recipes.md`
(next deliverable), then fanned out into per-asset briefs in `assets/`.

---

*Next deliverables (gated where noted): `recipes.md` (approve the per-kind make-it recipes) → `areas/`
A0–A5 blockouts **[gated on the elevation bake contract]** → `assets/` briefs **[same gate]** →
`asset_index.md`. The creative direction above is buildable now; the terrain geometry waits on the
engine program.*
