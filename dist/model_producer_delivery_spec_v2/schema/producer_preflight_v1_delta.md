# producer_preflight_v1 Schema Notes

Required file:

```text
preflight_report.json
```

Required fields:

```yaml
preflight_report_version:
  const: producer_preflight_v1

producer_spec_version:
  string

asset_id:
  string

texture_mode:
  enum:
    - flat_region
    - textured

ok:
  boolean

tool_versions:
  object

checks:
  required:
    - geometry
    - texture
    - rig_skin
    - animation
    - hitbox
    - bake

artifacts:
  object
```

Rule:

```text
ok must be false if any required stage status is fail.
```
