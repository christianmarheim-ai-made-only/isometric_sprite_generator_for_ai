# Generating hitbox data (from the model)

**Audience:** whoever (a human or an AI) produces the **hit / collision data** for a body. The point
of this stage: it is **100% derivable from the model's own geometry** — no art judgement, just
min/max over known vertices — so an AI can compute it directly, by raw iteration, in one pass.

There are **two** pieces of hit data, both derived from the model, plus one optional compact text
artifact that bundles them:

| Output | Derived from | Who produces it |
|---|---|---|
| **R8 hit-mask** (per-pixel region map: head/torso/arms/legs) | the **region-tagged faces** (material names) | the renderer, automatically, at bake time |
| **`world_metrics`** (the collision capsule: height, footprint radius, eye) | the body's **vertex AABB** | the baker, automatically; you can override |
| **`hitbox_v1` JSON** (capsule + per-region world AABBs) | the same vertices | `hitbox_from_mesh.py`, or an AI by hand |

You do **not** paint or place hitboxes by eye. You **tag** the geometry by region (already done in
[`modeling_the_body.md`](modeling_the_body.md)) and **measure** the rest.

---

## 1. The R8 hit-mask — comes from region tags, free

Every face already carries a HIT region from its **material name** (head/torso/arms/legs — the
keyword table is in [`modeling_the_body.md`](modeling_the_body.md)). The renderer bakes those tags
into a per-pixel **R8 mask atlas** (palette `none 0 / head 1 / torso 2 / arms 3 / legs 4`), one
region id per pixel, aligned to the color sprite. **There is nothing extra to author** — if the
materials are named right, the mask is correct. Verify it on the `*_hit_sheet.png`
(head=red/torso=green/arms=blue/legs=yellow). Body-only this iteration: ids `1..4` only; `5..7`
(weapon/shield/gear) are reserved and rejected.

## 2. The collision capsule (`world_metrics`) — measured from the AABB

The engine collides/positions the character with a simple upright **capsule** described by
`world_metrics` (metres, +Z up, origin at the foot). All three numbers are pure min/max over the
model's vertices:

```text
height_world           = max(z) over all verts                       # top of the body above ground
footprint_radius_world = max(|x|,|y|) over GROUND-CONTACT verts only  # verts with z <= 0.15 * height
eye_height_world       = head/eye socket z, else 0.9 * height_world   # must be <= height_world
```

Two rules that matter:

- **Footprint = ground contact, not the widest cross-section.** Use only the verts near the floor
  (`z <= 0.15 * height`). An out-flung arm or a wing must **not** inflate the collision radius — the
  capsule is what the body stands in, not its silhouette. (See
  [`world_metrics_policy.md`](world_metrics_policy.md).)
- **Exclude equipment** from the proxy — held weapons, shields, capes, backpacks, VFX. Body-only
  this iteration, so this is automatic, but the rule stays (ADR-0007).

`height_world > 0`, `footprint_radius_world > 0`, `eye_height_world <= height_world`, or the package
is rejected (Gate-1).

## 3. The compact artifact — `hitbox_v1` JSON

Bundle the capsule + a per-region world **AABB** (the coarse box of each body part's vertices) into
one small file. Schema: `pipeline/schema/hitbox_spec.schema.json`. Example:
`pipeline/examples/hitbox/humanoid_hitbox.json`. Shape:

```json
{
  "hitbox_spec_version": "hitbox_v1",
  "unit": "meter", "up": "z",
  "world_metrics": { "height_world": 1.8, "footprint_radius_world": 0.3, "eye_height_world": 1.62, "unit": "meter" },
  "collision_capsule": { "radius_world": 0.3, "height_world": 1.8 },
  "regions": {
    "head":  { "id": 1, "aabb_min": [-0.19,-0.12,1.46], "aabb_max": [0.23,0.12,1.8] },
    "torso": { "id": 2, "aabb_min": [-0.23,-0.24,0.88], "aabb_max": [0.23,0.24,1.46] },
    "arms":  { "id": 3, "aabb_min": [...], "aabb_max": [...] },
    "legs":  { "id": 4, "aabb_min": [...], "aabb_max": [...] }
  }
}
```

The per-region AABB is the cheap "is this hit in the head box?" volume; the **authoritative** per-hit
answer is still the R8 mask. Each `aabb_min/max` is just `min`/`max` of that region's vertices.

---

## Generate it

**With the tool** (numpy, no Blender):

```text
python pipeline/tools/hitbox_from_mesh.py your_body.obj --out your_hitbox.json
```

It loads the OBJ (regions by material/group name), computes the capsule exactly the way the baker
does, and the per-region AABBs, and prints/writes the JSON.

**By hand / by an AI** — there is no DCC step; it is arithmetic over the vertex list:

1. Read the verts (and each face's region tag).
2. `height = max z`. Translate so `min z = 0` if not already (origin at the foot).
3. `ground = verts with z <= 0.15*height`; `footprint_radius = max(|x|,|y|)` over `ground`.
4. `eye = 0.9*height` (or the head socket z).
5. For each region id, gather its faces' verts; `aabb_min/max = min/max` of those.

That's the whole computation — small, exact, iterable.

---

## Verify

- [ ] `height_world` ≈ the model's real height in metres; `footprint_radius_world` is the
      stance radius (not the arm span); `eye_height_world <= height_world`.
- [ ] After a bake, the manifest's `world_metrics` **matches** your derived numbers (the tool uses
      the same formula the baker does — for the example, both read `1.8 / 0.3 / 1.62`).
- [ ] The `*_hit_sheet.png` shows head/torso/arms/legs covering the silhouette (the R8 mask is
      right ⇒ the region tags are right).

## Where this fits

The model's geometry is the single source: region-tagged faces → the R8 mask, the vertex AABB → the
collision capsule. So the same one pass that builds the body yields its hit data. Continue with
[`generating_animation_data.md`](generating_animation_data.md) (motion from the rig) and
[`external_asset_contract.md`](external_asset_contract.md) (the asset manifest).
