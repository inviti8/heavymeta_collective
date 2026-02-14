# 3D_RESEARCH.md — NiceGUI 3D Scene Capabilities & Card Visualization

## Purpose

Research document evaluating NiceGUI's 3D capabilities for two features:

1. **Card Customization** — 3D card model with user-applied textures (front/back), realistic materials, lighting control
2. **Card Wallet** — Multiple 3D cards in a browsable layout with scroll-driven animations and click-to-flip interaction

---

## Table of Contents

- [NiceGUI `ui.scene` Overview](#nicegui-uiscene-overview)
- [Available 3D Objects](#available-3d-objects)
- [Lighting](#lighting)
- [Materials & Textures](#materials--textures)
- [Camera & Controls](#camera--controls)
- [Event Handling (Click, Drag)](#event-handling-click-drag)
- [Animation](#animation)
- [JavaScript Interop & Escape Hatches](#javascript-interop--escape-hatches)
- [The Standalone Three.js Approach](#the-standalone-threejs-approach)
- [Card-Specific Techniques](#card-specific-techniques)
- [Scroll-Driven Animation](#scroll-driven-animation)
- [Recommendation for Heavymeta](#recommendation-for-heavymeta)
- [References & Links](#references--links)

---

## NiceGUI `ui.scene` Overview

**NiceGUI version:** 3.7.1
**Three.js version bundled:** 0.180.0
**Animation library:** Tween.js 25.0.0 (camera movement only)

`ui.scene` is a Vue.js component wrapping Three.js. Python creates/modifies a scene graph on the server; commands flow to the browser over WebSocket via `run_method()`. The render loop runs at a configurable FPS (default 20).

```python
ui.scene(
    width=400,
    height=300,
    grid=True,                          # GridHelper (100x100)
    camera=ui.scene.perspective_camera(),
    on_click=handler,
    click_events=['click', 'dblclick'],
    on_drag_start=handler,
    on_drag_end=handler,
    drag_constraints='',                # JS expressions: 'x = 0, z = y / 2'
    background_color='#eee',
    fps=20,                             # target frame rate
    show_stats=False,                   # Three.js Stats overlay
)
```

### Bundled Three.js Modules

| Module | Purpose |
|--------|---------|
| `THREE` (core) | Scene, camera, renderer, geometry, materials |
| `OrbitControls` | Mouse-based camera orbit/pan/zoom |
| `DragControls` | Object dragging |
| `GLTFLoader` | glTF/GLB model loading |
| `STLLoader` | STL mesh loading |
| `CSS2DRenderer` | Billboard 2D text |
| `CSS3DRenderer` | 3D-positioned text |
| `TWEEN` | Camera animation tweening |
| `Stats` | Performance monitoring |

### Internal Properties (accessible via JavaScript)

```javascript
const el = getElement(scene_id);
el.scene        // THREE.Scene
el.camera       // THREE.PerspectiveCamera or THREE.OrthographicCamera
el.renderer     // THREE.WebGLRenderer
el.controls     // OrbitControls
el.objects      // Map<string, THREE.Object3D>
el.texture_loader  // THREE.TextureLoader
el.gltf_loader     // GLTFLoader
el.stl_loader      // STLLoader
```

Source: [NiceGUI ui.scene docs](https://nicegui.io/documentation/scene) | [scene.js source](https://github.com/zauberzeug/nicegui/blob/main/nicegui/elements/scene/scene.js)

---

## Available 3D Objects

Every object inherits from `Object3D` and supports `.move()`, `.rotate()`, `.scale()`, `.material()`, `.visible()`, `.draggable()`, `.with_name()`, `.delete()`.

| Python API | Three.js Basis | Key Parameters |
|------------|----------------|----------------|
| `scene.box()` | BoxGeometry | `width=1, height=1, depth=1, wireframe=False` |
| `scene.sphere()` | SphereGeometry | `radius=1, width_segments=32, height_segments=16` |
| `scene.cylinder()` | CylinderGeometry | `top_radius=1, bottom_radius=1, height=1` |
| `scene.ring()` | RingGeometry | `inner_radius=0.5, outer_radius=1.0` |
| `scene.extrusion()` | ExtrudeGeometry | `outline: [[x,y],...], height` |
| `scene.line()` | Line | `start, end` (3D points) |
| `scene.curve()` | CubicBezierCurve3 | `start, control1, control2, end` |
| `scene.quadratic_bezier_tube()` | TubeGeometry | `start, mid, end, radius=1.0` |
| `scene.stl()` | STLLoader | `url` |
| `scene.gltf()` | GLTFLoader | `url` |
| `scene.texture()` | Mesh + TextureLoader | `url, coordinates` (UV-mapped grid) |
| `scene.text()` | CSS2DObject | `text, style` (billboard) |
| `scene.text3d()` | CSS3DObject | `text, style` (3D positioned) |
| `scene.point_cloud()` | Points | `points, colors, point_size` |
| `scene.spot_light()` | SpotLight | `color, intensity, distance, angle, penumbra, decay` |
| `scene.group()` | Group | context manager for hierarchy |
| `scene.axes_helper()` | AxesHelper | `length=1.0` |

### Object3D Methods

```python
obj.move(x=0, y=0, z=0)
obj.rotate(r_x, r_y, r_z)          # Euler angles (radians)
obj.scale(sx=1, sy=None, sz=None)   # sy/sz default to sx
obj.material(color='#ff0000', opacity=1.0, side='front')  # 'front'|'back'|'both'
obj.visible(True)
obj.draggable(True)
obj.with_name('my_object')
obj.attach(parent_obj)              # reparent preserving world transform
obj.detach()                        # back to scene root
obj.delete()
```

---

## Lighting

### Hard-Coded Default Lights (NOT configurable via Python)

```javascript
// Always created in scene.js:
scene.add(new THREE.AmbientLight(0xffffff, 0.7 * Math.PI));   // ~2.2 intensity
const light = new THREE.DirectionalLight(0xffffff, 0.3 * Math.PI);  // ~0.94
light.position.set(5, 10, 40);
scene.add(light);
```

### Exposed Light Type: SpotLight Only

```python
scene.spot_light(
    color='#ffffff',
    intensity=1.0,
    distance=0.0,       # 0 = infinite range
    angle=math.pi/3,    # cone angle
    penumbra=0.0,        # edge softness
    decay=1.0,           # attenuation
).move(5, 5, 5)
```

### NOT Exposed via Python API

- PointLight
- DirectionalLight (only the hard-coded default)
- HemisphereLight
- RectAreaLight

### Workaround: Remove/Replace Default Lights via JavaScript

From [Discussion #3917](https://github.com/zauberzeug/nicegui/discussions/3917):

```python
with ui.scene() as scene:
    scene.sphere()

def setup_lights():
    ui.run_javascript(f'''
        const el = getElement({scene.id});
        // Remove default ambient + directional (first two children)
        el.scene.children.slice(0, 2).forEach(c => c.removeFromParent());

        // Add custom lights (use numeric constants since THREE is module-scoped)
        // PointLight: THREE.PointLight is not directly accessible, but
        // objects can be created via the scene's Three.js context
    ''')

scene.on('init', setup_lights)
```

**Verdict:** Lighting control is limited. For full control, need JavaScript injection or the standalone approach.

---

## Materials & Textures

### Native Material API

```python
obj.material(
    color='#ff0000',    # CSS color string, or None for vertex colors
    opacity=0.5,        # 0.0-1.0 (transparent=true always set)
    side='both',        # 'front', 'back', or 'both'
)
```

### Material Types (Hard-Coded in scene.js)

| Object Type | Material Used | Limitations |
|-------------|--------------|-------------|
| Solid geometry (box, sphere, etc.) | `MeshPhongMaterial` | Color + opacity only |
| Wireframes | `LineBasicMaterial` | Color + opacity only |
| Texture meshes | `MeshLambertMaterial` with texture map | Image texture on UV grid |
| GLTF models | Embedded materials | Full PBR if baked into GLB |
| Point clouds | `PointsMaterial` | Color + size |

### What is NOT Supported

- `MeshStandardMaterial` (PBR)
- `MeshPhysicalMaterial` (clearcoat, iridescence)
- Custom shaders / `ShaderMaterial`
- Normal maps, roughness maps, metalness maps, environment maps
- Multi-material per object (different materials per face)
- Image textures on primitives (box, sphere, etc.)

Confirmed by NiceGUI maintainer in [Discussion #4120](https://github.com/zauberzeug/nicegui/discussions/4120): *"Custom shaders are currently not supported."*

### The `scene.texture()` Object

A special mesh that maps an image onto a grid of 3D coordinates:

```python
# coordinates: 2D grid of [x,y,z] points defining the surface
scene.texture(
    url='/static/card_front.png',
    coordinates=[
        [[0, 0, 0], [1, 0, 0], [2, 0, 0]],
        [[0, 1, 0], [1, 1, 0],   [2, 1, 0]],
        [[0, 2, 0], [1, 2, 0], [2, 2, 0]],
    ]
)
```

Dynamic updates at runtime:

```python
tex.set_url('/static/new_image.png')         # swap image
tex.set_coordinates(new_coords)               # update mesh
```

### GLTF Models Preserve Embedded Materials

GLTF/GLB files loaded with `scene.gltf()` keep their embedded PBR materials intact. This is the **best path** for realistic rendering — bake materials in Blender, export as GLB.

```python
scene.gltf('/static/models/card.glb').scale(1.0).move(0, 0, 0)
```

### Applying Textures to Primitives via JavaScript (Workaround)

```python
with ui.scene() as scene:
    box = scene.box(2, 2, 2)

async def apply_texture():
    await ui.run_javascript(f'''
        const el = getElement({scene.id});
        const obj = el.objects.get("{box.id}");
        el.texture_loader.load('/static/crate.png', (texture) => {{
            obj.material.map = texture;
            obj.material.needsUpdate = true;
        }});
    ''')

scene.on('init', apply_texture)
```

---

## Camera & Controls

### Camera Types

```python
# Perspective (default)
camera = ui.scene.perspective_camera(fov=75, near=0.1, far=1000)

# Orthographic
camera = ui.scene.orthographic_camera(size=10, near=0.1, far=1000)

scene = ui.scene(camera=camera)
```

### Camera Methods

```python
# Animated camera movement (Tween.js interpolation)
scene.move_camera(
    x=5, y=5, z=5,
    look_at_x=0, look_at_y=0, look_at_z=0,
    up_x=0, up_y=0, up_z=1,
    duration=0.5,   # seconds; 0 = instant
)

# Query current state (async)
camera_data = await scene.get_camera()
# Returns: { position, up, rotation, quaternion, fov, aspect, near, far, ... }
```

### OrbitControls (Automatic)

- Left-click drag: orbit/rotate
- Right-click drag: pan
- Scroll wheel: zoom
- Auto-disabled during object drag

No Python API to configure OrbitControls parameters. Use `run_javascript` to adjust:

```python
ui.run_javascript(f'''
    const el = getElement({scene.id});
    el.controls.enableDamping = true;
    el.controls.dampingFactor = 0.05;
    el.controls.minDistance = 2;
    el.controls.maxDistance = 20;
''')
```

### SceneView — Multiple Views of One Scene

```python
scene = ui.scene()
# ...add objects...
view = ui.scene_view(scene, width=400, height=300,
                     camera=ui.scene.orthographic_camera(size=5))
```

---

## Event Handling (Click, Drag)

### Click Events — Full Raycasting Support

```python
def handle_click(e: SceneClickEventArguments):
    print(f'Type: {e.click_type}')     # 'click' or 'dblclick'
    print(f'Button: {e.button}')        # 0=left, 1=middle, 2=right
    print(f'Modifiers: alt={e.alt}, ctrl={e.ctrl}, shift={e.shift}')
    for hit in e.hits:                  # sorted by distance, nearest first
        print(f'  Object: {hit.object_name} at ({hit.x:.2f}, {hit.y:.2f}, {hit.z:.2f})')

with ui.scene(on_click=handle_click) as scene:
    scene.box().with_name('Red Box').material('red')
    scene.sphere().move(3, 0, 0).with_name('Blue Sphere').material('blue')
```

### Drag Events

```python
def on_drag_end(e: SceneDragEventArguments):
    ui.notify(f'Dropped {e.object_name} at ({e.x:.1f}, {e.y:.1f}, {e.z:.1f})')

with ui.scene(on_drag_end=on_drag_end) as scene:
    box = scene.box().draggable()

# Constraint expressions (evaluated as JS):
scene = ui.scene(drag_constraints='z = 0')             # lock to z=0 plane
scene = ui.scene(drag_constraints='z = Math.max(0, z)') # can't go below 0
```

---

## Animation

### Built-In: Camera Only

`move_camera(duration=...)` uses Tween.js. No object animation API exists.

### Server-Side Animation via `ui.timer` (Python-Driven)

```python
import math, time
from nicegui import ui

with ui.scene(fps=30) as scene:
    box = scene.box().material('red')

start = time.time()

def animate():
    t = time.time() - start
    box.move(2 * math.sin(t), 0, 1 + 0.5 * math.sin(t * 2))
    box.rotate(0, t, 0)

ui.timer(1/30, animate)
```

**Latency:** Each frame round-trips through Python -> WebSocket -> Browser. Works for simple animations at ~20-30 FPS but will be choppy for complex scenes.

### Client-Side Animation via JavaScript (No Server Round-Trip)

```python
with ui.scene(fps=60) as scene:
    box = scene.box().material('#ff6600')

def setup_animation():
    ui.run_javascript(f'''
        const el = getElement({scene.id});
        const obj = el.objects.get("{box.id}");
        let start = Date.now();
        setInterval(() => {{
            const t = (Date.now() - start) / 1000;
            obj.position.x = 2 * Math.sin(t);
            obj.rotation.y = t;
        }}, 1000 / 60);
    ''')

scene.on('init', setup_animation)
```

### GLTF Animations: NOT Supported Natively

The GLTF loader in `scene.js` discards `gltf.animations`. No `AnimationMixer` is created.

```javascript
// What scene.js does (line 314):
this.gltf_loader.load(url, (gltf) => mesh.add(gltf.scene));
// gltf.animations is NEVER referenced
```

**Workaround:** Re-load the GLTF via JavaScript to access animations:

```python
async def play_gltf_animation():
    await ui.run_javascript(f'''
        const el = getElement({scene.id});
        el.gltf_loader.load('/static/animated.glb', (gltf) => {{
            el.scene.add(gltf.scene);
            const mixer = new THREE.AnimationMixer(gltf.scene);
            gltf.animations.forEach(clip => mixer.clipAction(clip).play());

            const clock = new THREE.Clock();
            setInterval(() => mixer.update(clock.getDelta()), 1000/60);
        }});
    ''')
```

**Caveat:** Objects added via raw JavaScript won't be tracked by Python, won't respond to `on_click`, and won't serialize on reconnect.

---

## JavaScript Interop & Escape Hatches

### `run_method()` — Call Vue Component Methods

```python
result = await scene.run_method('get_camera')
scene.run_method('move', object_id, x, y, z)   # fire-and-forget
```

Available methods: `create`, `name`, `material`, `move`, `scale`, `rotate`, `visible`, `draggable`, `delete`, `set_texture_url`, `set_texture_coordinates`, `set_points`, `attach`, `detach`, `move_camera`, `get_camera`, `init_objects`.

### `ui.run_javascript()` — Direct Three.js Access

```python
await ui.run_javascript(f'''
    const el = getElement({scene.id});
    el.renderer.setClearColor(0x000000);
    el.camera.fov = 60;
    el.camera.updateProjectionMatrix();
''')
```

### Critical Caveat: `THREE` is Module-Scoped

The `THREE` namespace is imported as an ES module inside `scene.js` but is **NOT a global variable**. When using `ui.run_javascript()`, you're in the global `window` scope where `THREE` doesn't exist.

**This means:** You cannot construct `new THREE.PointLight(...)` or `new THREE.ShaderMaterial(...)` from `ui.run_javascript()` unless you find the THREE reference through the component module scope.

**Workaround:** Use Three.js numeric constants instead of named constants:

| THREE Constant | Value |
|----------------|-------|
| `THREE.FrontSide` | `0` |
| `THREE.BackSide` | `1` |
| `THREE.DoubleSide` | `2` |
| `THREE.LinearToneMapping` | `1` |
| `THREE.ACESFilmicToneMapping` | `6` |
| `THREE.SRGBColorSpace` | `"srgb"` |

For constructing new Three.js objects, the standalone approach is more reliable.

---

## The Standalone Three.js Approach

For features beyond what `ui.scene` supports (custom shaders, PBR materials, GLTF animations, post-processing), bypass `ui.scene` entirely and embed a standalone Three.js app via `ui.add_body_html()`.

```python
from nicegui import app, ui

app.add_static_files('/models', 'static/models')
app.add_static_files('/textures', 'static/textures')

ui.add_head_html('''
<script type="importmap">
{
    "imports": {
        "three": "https://cdn.jsdelivr.net/npm/three@0.170.0/build/three.module.js",
        "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.170.0/examples/jsm/"
    }
}
</script>
''')

ui.add_body_html('''
<div id="card-scene" style="width:100%;height:600px;"></div>
<script type="module">
    import * as THREE from 'three';
    import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
    import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
    import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
    import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
    import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';

    const container = document.getElementById('card-scene');
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(
        45, container.clientWidth / container.clientHeight, 0.1, 100
    );
    camera.position.set(0, 0, 5);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.2;
    container.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;

    // Full lighting control
    scene.add(new THREE.AmbientLight(0xffffff, 0.4));
    const key = new THREE.DirectionalLight(0xffffff, 1.2);
    key.position.set(5, 10, 7);
    scene.add(key);
    const fill = new THREE.PointLight(0x8c52ff, 0.5, 20);
    fill.position.set(-3, 2, 4);
    scene.add(fill);

    // Post-processing
    const composer = new EffectComposer(renderer);
    composer.addPass(new RenderPass(scene, camera));
    composer.addPass(new UnrealBloomPass(
        new THREE.Vector2(800, 600), 0.3, 0.4, 0.85
    ));

    // GLTF with animations
    const loader = new GLTFLoader();
    let mixer;

    window.loadCardModel = function(url) {
        loader.load(url, (gltf) => {
            scene.add(gltf.scene);
            if (gltf.animations.length > 0) {
                mixer = new THREE.AnimationMixer(gltf.scene);
                gltf.animations.forEach(clip => mixer.clipAction(clip).play());
            }
        });
    };

    // Expose for Python interaction
    window.cardScene = scene;
    window.cardCamera = camera;

    const clock = new THREE.Clock();
    function animate() {
        requestAnimationFrame(animate);
        const delta = clock.getDelta();
        if (mixer) mixer.update(delta);
        controls.update();
        composer.render();
    }
    animate();
</script>
''')

# Python interaction:
ui.button('Load Card', on_click=lambda: ui.run_javascript(
    "loadCardModel('/models/card.glb')"
))
```

### Advantages Over `ui.scene`

| Feature | `ui.scene` | Standalone Three.js |
|---------|-----------|---------------------|
| PBR materials | No | Yes |
| Custom shaders | No | Yes |
| GLTF animations | No | Yes |
| Post-processing (bloom, AO) | No | Yes |
| Full lighting control | SpotLight only | All light types |
| Environment maps / HDR | No | Yes |
| Multi-material per object | No | Yes |
| `MeshPhysicalMaterial` (clearcoat, iridescence) | No | Yes |
| Click events on objects | Built-in | Manual raycasting |
| Python object tracking | Automatic | Manual via `window` globals |

### Disadvantages

- No automatic Python <-> JS object sync
- Click/drag events must be implemented manually (raycaster)
- No `scene.objects` dict — must manage references via `window` globals
- More JavaScript code to maintain

---

## Card-Specific Techniques

### Card Geometry — Rounded Rectangle

**ISO card dimensions:** 85.6mm x 53.98mm x 0.76mm (ratio ~1.586 : 1 : 0.014)

#### Option A: NiceGUI `scene.extrusion()` (Basic, No Textures)

```python
import math

def rounded_rect_outline(w, h, r, segments=8):
    """Generate 2D outline points for a rounded rectangle."""
    points = []
    corners = [
        (w/2 - r, -h/2 + r, -math.pi/2, 0),       # bottom-right
        (w/2 - r, h/2 - r, 0, math.pi/2),            # top-right
        (-w/2 + r, h/2 - r, math.pi/2, math.pi),     # top-left
        (-w/2 + r, -h/2 + r, math.pi, 3*math.pi/2),  # bottom-left
    ]
    for cx, cy, a_start, a_end in corners:
        for i in range(segments + 1):
            angle = a_start + (a_end - a_start) * i / segments
            points.append([cx + r * math.cos(angle), cy + r * math.sin(angle)])
    return points

with ui.scene() as scene:
    outline = rounded_rect_outline(3.2, 2.0, 0.12)
    card = scene.extrusion(outline, 0.03)
    card.material('#1a1a2e')
```

#### Option B: Three.js ExtrudeGeometry (Standalone Approach)

```javascript
function createRoundedRectShape(width, height, radius) {
    const shape = new THREE.Shape();
    const x = -width / 2, y = -height / 2;

    shape.moveTo(x + radius, y);
    shape.lineTo(x + width - radius, y);
    shape.quadraticCurveTo(x + width, y, x + width, y + radius);
    shape.lineTo(x + width, y + height - radius);
    shape.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
    shape.lineTo(x + radius, y + height);
    shape.quadraticCurveTo(x, y + height, x, y + height - radius);
    shape.lineTo(x, y + radius);
    shape.quadraticCurveTo(x, y, x + radius, y);

    return shape;
}

const shape = createRoundedRectShape(3.2, 2.0, 0.12);
const geometry = new THREE.ExtrudeGeometry(shape, {
    depth: 0.03,
    bevelEnabled: true,
    bevelThickness: 0.005,
    bevelSize: 0.005,
    bevelSegments: 3
});
```

#### Option C: GLTF/GLB Model from Blender (Recommended for Production)

Model the card in Blender with proper edge rounding, assign separate materials for front/back faces, bake PBR textures, export as GLB. NiceGUI loads it with all materials intact via `scene.gltf()`.

### Front/Back Textures

#### Material Array on BoxGeometry (Standalone Three.js)

```javascript
const loader = new THREE.TextureLoader();
const frontTex = loader.load('/textures/card_front.png');
const backTex = loader.load('/textures/card_back.png');
const edgeMat = new THREE.MeshStandardMaterial({ color: 0x333333 });

// BoxGeometry: 6 faces = [+X, -X, +Y, -Y, +Z (front), -Z (back)]
const materials = [
    edgeMat, edgeMat, edgeMat, edgeMat,
    new THREE.MeshStandardMaterial({ map: frontTex }),
    new THREE.MeshStandardMaterial({ map: backTex }),
];
const card = new THREE.Mesh(new THREE.BoxGeometry(3.2, 2.0, 0.03), materials);
```

#### Two Overlapping Planes (works with ExtrudeGeometry)

```javascript
const cardBody = new THREE.Mesh(extrudedGeometry, bodyMaterial);

const frontPlane = new THREE.Mesh(
    new THREE.PlaneGeometry(3.2, 2.0),
    new THREE.MeshStandardMaterial({ map: frontTex })
);
frontPlane.position.z = 0.016;

const backPlane = new THREE.Mesh(
    new THREE.PlaneGeometry(3.2, 2.0),
    new THREE.MeshStandardMaterial({ map: backTex })
);
backPlane.position.z = -0.001;
backPlane.rotation.y = Math.PI;

const cardGroup = new THREE.Group();
cardGroup.add(cardBody, frontPlane, backPlane);
```

### Realistic Card Materials

```javascript
// Glossy (laminated credit card)
new THREE.MeshPhysicalMaterial({
    map: cardTexture,
    roughness: 0.1,
    metalness: 0.0,
    clearcoat: 1.0,
    clearcoatRoughness: 0.05,
    reflectivity: 0.9,
});

// Matte (business card)
new THREE.MeshStandardMaterial({
    map: cardTexture,
    roughness: 0.8,
    metalness: 0.0,
});

// Metallic (premium card)
new THREE.MeshPhysicalMaterial({
    map: cardTexture,
    roughness: 0.2,
    metalness: 1.0,
    clearcoat: 0.5,
    envMapIntensity: 1.5,  // needs environment map
});
```

### Holographic / Iridescent Effects

Several community libraries:

- **[threejs-vanilla-holographic-material](https://github.com/ektogamat/threejs-vanilla-holographic-material)** — Drop-in holographic material with scanlines, Fresnel, and blink effects. Call `.update()` in render loop.
- **[threejs-thin-film-iridescence](https://github.com/DerSchmale/threejs-thin-film-iridescence)** — Physics-based thin-film iridescence via lookup texture.
- **[Foil sticker shader tutorial](https://www.4rknova.com/blog/2025/08/30/foil-sticker)** — Complete GLSL shader for metallic foil with flakes and environment mapping.

---

## Card Flip Animation

### GSAP (Recommended)

```javascript
import gsap from 'gsap';

let isFlipped = false;
function flipCard(cardMesh) {
    isFlipped = !isFlipped;
    gsap.to(cardMesh.rotation, {
        y: isFlipped ? Math.PI : 0,
        duration: 0.8,
        ease: "power2.inOut"
    });
}
```

### Quaternion Slerp (Avoids Gimbal Lock for Complex Rotations)

```javascript
const progress = { t: 0 };
const startQuat = new THREE.Quaternion().setFromEuler(new THREE.Euler(0, 0, 0));
const endQuat = new THREE.Quaternion().setFromEuler(new THREE.Euler(0, Math.PI, 0));

gsap.to(progress, {
    t: 1,
    duration: 0.8,
    ease: "power2.inOut",
    onUpdate: () => {
        cardMesh.quaternion.slerpQuaternions(startQuat, endQuat, progress.t);
    }
});
```

### Card Wallet Layouts

**Stacked Deck:**
```javascript
cards.forEach((card, i) => {
    card.position.z = i * 0.005;
    card.position.x = i * 0.002;
    card.position.y = -i * 0.002;
});
```

**Fan Spread:**
```javascript
function fanCards(cards, spreadAngle = 30, radius = 3) {
    const total = THREE.MathUtils.degToRad(spreadAngle);
    const start = -total / 2;
    cards.forEach((card, i) => {
        const angle = start + (total * i / (cards.length - 1));
        gsap.to(card.position, {
            x: Math.sin(angle) * radius,
            y: Math.cos(angle) * radius - radius,
            duration: 0.6, ease: "power2.out", delay: i * 0.05
        });
        gsap.to(card.rotation, {
            z: -angle,
            duration: 0.6, ease: "power2.out", delay: i * 0.05
        });
    });
}
```

**Carousel:**
```javascript
function arrangeCarousel(cards, radius = 5) {
    const step = (2 * Math.PI) / cards.length;
    cards.forEach((card, i) => {
        const angle = step * i;
        gsap.to(card.position, {
            x: Math.sin(angle) * radius,
            z: Math.cos(angle) * radius,
            duration: 1, ease: "power2.inOut"
        });
        gsap.to(card.rotation, { y: angle, duration: 1, ease: "power2.inOut" });
    });
}
```

---

## Scroll-Driven Animation

### Pure Three.js Scroll Binding

```javascript
let scrollPercent = 0;

document.addEventListener('scroll', () => {
    scrollPercent = document.documentElement.scrollTop /
        (document.documentElement.scrollHeight - document.documentElement.clientHeight);
});

const animations = [
    { start: 0.0, end: 0.33, fn: (t) => { /* fan out cards */ } },
    { start: 0.33, end: 0.66, fn: (t) => { /* flip featured card */ } },
    { start: 0.66, end: 1.0, fn: (t) => { /* carousel rotation */ } },
];

function playScrollAnimations() {
    animations.forEach(({ start, end, fn }) => {
        if (scrollPercent >= start && scrollPercent < end) {
            fn((scrollPercent - start) / (end - start));
        }
    });
}

// Call in render loop
function animate() {
    requestAnimationFrame(animate);
    playScrollAnimations();
    renderer.render(scene, camera);
}
```

Source: [sbcode.net — Animate on Scroll](https://sbcode.net/threejs/animate-on-scroll/)

### GSAP ScrollTrigger (More Robust)

```javascript
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
gsap.registerPlugin(ScrollTrigger);

ScrollTrigger.create({
    trigger: "#card-scene",
    start: "top top",
    end: "+=3000",      // 3000px of scroll distance
    pin: true,
    scrub: 1,            // smooth scrubbing
    onUpdate: (self) => {
        const progress = self.progress;  // 0 to 1
        // Map progress to card animations
        updateCardPositions(progress);
    }
});
```

Sources: [Codrops — Cinematic 3D Scroll](https://tympanus.net/codrops/2025/11/19/how-to-build-cinematic-3d-scroll-experiences-with-gsap/) | [Three.js Journey — Scroll Animation](https://threejs-journey.com/lessons/scroll-based-animation)

### NiceGUI Scroll Integration

Within NiceGUI, use `ui.scroll_area` + JavaScript event listener:

```python
with ui.scene(fps=30) as scene:
    box = scene.box()

scroll_area = ui.scroll_area().classes('w-full h-screen')
with scroll_area:
    ui.html('<div style="height: 5000px;"></div>')

ui.add_head_html(f'''
<script>
document.addEventListener('DOMContentLoaded', () => {{
    const scrollEl = document.querySelector('.q-scrollarea__container');
    if (scrollEl) {{
        scrollEl.addEventListener('scroll', () => {{
            const progress = scrollEl.scrollTop /
                (scrollEl.scrollHeight - scrollEl.clientHeight);
            const el = getElement({scene.id});
            if (el && el.objects) {{
                el.objects.forEach((obj, id) => {{
                    obj.rotation.y = progress * Math.PI * 4;
                }});
            }}
        }});
    }}
}});
</script>
''')
```

---

## Recommendation for Heavymeta

### Capability Matrix

| Requirement | `ui.scene` Native | `ui.scene` + JS Injection | Standalone Three.js |
|-------------|:-:|:-:|:-:|
| Display 3D card model | Yes (GLTF) | -- | Yes |
| Apply user textures to card | No | Partial | Yes |
| Realistic materials (PBR, clearcoat) | No | No | Yes |
| Holographic / iridescent effects | No | No | Yes |
| Full lighting control | No | Partial | Yes |
| Click to flip card | Yes (click event) | Yes (animation) | Yes |
| Scroll-driven layout animations | No | Hacky | Yes |
| GLTF animations | No | Fragile | Yes |
| Post-processing (bloom) | No | No | Yes |
| Card wallet (multiple cards, fan/stack) | Partial | Partial | Yes |
| Python-side object tracking | Automatic | Automatic | Manual |
| Click raycasting | Built-in | Built-in | Manual |

### Recommended Architecture

**Use the standalone Three.js approach** embedded in NiceGUI via `ui.add_body_html()` with an ES module import map. This gives full Three.js power for the card visualization while the rest of the app stays in NiceGUI.

#### Implementation Path

1. **Model a card in Blender** — Rounded-rectangle mesh with two material slots (front/back). Export as GLB without textures baked in (they'll be applied dynamically).

2. **Create a reusable `CardScene` JavaScript module** loaded via `ui.add_body_html()`:
   - Loads the card GLB model
   - Applies user textures dynamically (front/back face images from IPFS CIDs)
   - Supports `MeshPhysicalMaterial` with clearcoat for glossy card look
   - Full lighting rig (ambient + directional key + fill)
   - Optional bloom post-processing for holographic effects
   - Exposes `window.cardScene` API for Python interaction

3. **Card Customization page** — Single card, orbit controls, real-time texture preview:
   - User uploads front/back images -> pin to IPFS -> apply to 3D card
   - Material picker (glossy, matte, metallic)
   - Python calls `ui.run_javascript("updateCardTexture('front', '/ipfs/<cid>')")` on change

4. **Card Wallet page** — Multiple cards with scroll-driven layout:
   - Load user's card + peer cards
   - GSAP ScrollTrigger drives stack -> fan -> carousel transitions
   - Click a card -> flip animation, show back details
   - Python handles click events via `window` callbacks back to server

5. **Communicate Python <-> JS** via:
   - Python -> JS: `ui.run_javascript("window.cardScene.doSomething(...)")`
   - JS -> Python: `emitEvent('card-clicked', { cardId })` or hidden NiceGUI elements

### Why Not Pure `ui.scene`?

The card features require PBR materials, multi-material objects, dynamic texture application to geometry faces, and smooth client-side animations — none of which are available through the `ui.scene` Python API. The JavaScript injection workarounds are fragile (module-scoped `THREE` problem) and don't compose well. A clean standalone Three.js module gives us full control while still living inside the NiceGUI page.

---

## References & Links

### NiceGUI Documentation
- [ui.scene](https://nicegui.io/documentation/scene) — Official scene docs
- [ui.run_javascript](https://nicegui.io/documentation/run_javascript) — JS interop docs
- [3D Scene Examples](https://github.com/zauberzeug/nicegui/tree/main/examples/3d_scene/) — Official examples

### NiceGUI GitHub Discussions
- [#4120 — Custom Shader Support](https://github.com/zauberzeug/nicegui/discussions/4120) — Confirmed not supported
- [#3917 — Lighting Parameters](https://github.com/zauberzeug/nicegui/discussions/3917) — Light removal workaround
- [#1892 — Texture Data](https://github.com/zauberzeug/nicegui/discussions/1892) — Texture discussion
- [#1269 — Geometry Updates](https://github.com/zauberzeug/nicegui/discussions/1269) — Dynamic geometry

### Three.js Card Projects
- [lnardon/3DCreditCard](https://github.com/lnardon/3DCreditCard) — 3D credit card with OBJ model
- [Andreloui5/3DCreditCardForm](https://github.com/Andreloui5/3DCreditCardForm) — 3D card form
- [Codrops — 3D Cards in Webflow](https://tympanus.net/codrops/2025/05/31/building-interactive-3d-cards-in-webflow-with-three-js/) — GLB card models
- [WebGL Apple Cards (CodePen)](https://codepen.io/smpnjn/pen/mdrWPpK) — Shader-driven cards

### Materials & Effects
- [threejs-vanilla-holographic-material](https://github.com/ektogamat/threejs-vanilla-holographic-material) — Drop-in holographic shader
- [threejs-thin-film-iridescence](https://github.com/DerSchmale/threejs-thin-film-iridescence) — Physics-based iridescence
- [Foil Sticker Shader](https://www.4rknova.com/blog/2025/08/30/foil-sticker) — GLSL foil/holographic effect
- [three-rounded-box](https://www.npmjs.com/package/three-rounded-box) — RoundedBoxGeometry

### Scroll Animation
- [sbcode.net — Animate on Scroll](https://sbcode.net/threejs/animate-on-scroll/) — Pure Three.js scroll
- [GSAP ScrollTrigger](https://gsap.com/docs/v3/Plugins/ScrollTrigger/) — Industry-standard scroll animation
- [Codrops — Cinematic 3D Scroll](https://tympanus.net/codrops/2025/11/19/how-to-build-cinematic-3d-scroll-experiences-with-gsap/) — GSAP + Three.js
- [Three.js Journey — Scroll Animation](https://threejs-journey.com/lessons/scroll-based-animation) — Tutorial

### Architecture References
- [DeepWiki — NiceGUI 3D Scene](https://deepwiki.com/zauberzeug/nicegui/3.6-3d-scene) — Architecture overview
- [NiceGUI scene.js source](https://github.com/zauberzeug/nicegui/blob/main/nicegui/elements/scene/scene.js) — Client-side implementation
