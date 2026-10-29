# L-Object

A Cinema 4D plugin that creates a stage for your test and final renders: a floor with a rounded front edge, a back wall and an optional top, all in one object.

More on [safina3d.blogspot.com](https://safina3d.blogspot.com).

![L-Object stage](https://raw.githubusercontent.com/safina3d/c4d-l-object/master/images/stage.png)

## Features

- One object for many stages: L, C, cyclorama, table...
- Smooth rounded corners
- Presets in one click: **L**, **C**, **Cyclo** and **Table**
- Optional thickness and side panels
- A different material for each part (floor, wall, top...)
- Ready for textures
- Handles in the viewport

## Requirements

- Cinema 4D R23 or later
- Tested with Cinema 4D 2023

## Installation

1. Copy the `L-Object` folder into the Cinema 4D plugins folder:
   - Windows: `C:\Program Files\Maxon Cinema 4D <version>\plugins\`
   - macOS: `/Applications/Maxon Cinema 4D <version>/plugins/`
2. Restart Cinema 4D.

You can also add the folder in `Preferences > Plugins > Plugin Folders`.

## Usage

Create the object from the **Extensions** menu (**Plugins** in older versions): **L-Object**.

### Parameters

Side view of the stage:

```
                       Top Depth
                 <------------------->
                  ___________________    -
                                     \   Top Curve Radius
                                     |
                                     |   Wall Height
                     Floor Depth     |
           <------------------------>|
             ____________________    /   Back Curve Radius
           /                             floor level
           | Front Curve Radius
           |
           | Front Height
```

| Parameter | Description |
|---|---|
| Width | Width of the stage |
| Thickness | Thickness of the stage. 0: no thickness |
| Left Side / Right Side | Closes the stage with a side panel |
| Floor Depth | Depth of the floor |
| Front Height | Height of the front edge, below the floor |
| Front Curve Radius | Curve between the front edge and the floor |
| Wall Height | Height of the back wall |
| Back Curve Radius | Curve between the floor and the wall |
| Top Depth | Depth of the top. 0: no top |
| Top Curve Radius | Curve between the wall and the top |
| Width Segments | Subdivisions along the width |
| Curve Segments | Smoothness of the curves |

A curve can't be larger than the parts it joins: increasing it beyond that also enlarges them. For example, a larger **Top Curve Radius** can raise the wall.

### Presets

| L | C | Cyclo | Table |
|---|---|---|---|
| ![L](https://raw.githubusercontent.com/safina3d/c4d-l-object/master/images/preset-l.png) | ![C](https://raw.githubusercontent.com/safina3d/c4d-l-object/master/images/preset-c.png) | ![Cyclo](https://raw.githubusercontent.com/safina3d/c4d-l-object/master/images/preset-cyclo.png) | ![Table](https://raw.githubusercontent.com/safina3d/c4d-l-object/master/images/preset-table.png) |

The **L**, **C**, **Cyclo** and **Table** buttons change the shape of the stage. The width, thickness, side panels and subdivisions are kept. Use **Undo** to go back.

### Handles

- Hover a handle to see its parameter and value.
- Drag it to change the value.
- Curve handles slow down when the curve reaches its maximum size.
- Hold **Ctrl** to ignore the handles.

### Materials

Each part of the stage has its own selection: `Front`, `Floor`, `Wall`, `Top`, `Sides` (side panels) and `Outside` (thickness).

To use a different material on a part, type its name in the **Selection** field of the material tag.

## Changelog

- V3.0
  - Presets: L, C, Cyclo, Table
  - Thickness and side panels
  - Smoother, perfectly round curves, with adjustable smoothness
  - A selection per part, for materials
  - Clearer parameter names, in sections. Existing scenes still open
  - Easier handles: bigger, easier to grab, with the parameter name and value on hover
  - Faster
  - Fixes: render and Team Render, inconsistent values, memory use

- V2.0
  - R23 update
  - Shape improvement (L to C)

- V1.1
  - R22 fix
  - UI language fix

- V1.0
