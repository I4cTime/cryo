#version 440

// Window frost driven by one number. The growth map (frost_growth.png) holds
// R = freeze order, G = crystal detail, B = sparkle. Everything with
// R below `amount` is frozen; the caller animates `amount`, there is no
// time uniform. Keep the maths in sync with shade_frame() in
// tools/gen_frost.py, which bakes the software-renderer fallback.
// Rebuild the .qsb with tools/build_shaders.py after editing.

layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;

layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    float amount;        // 0 = clear pane, 1 = fully frosted
    float intensity;     // maximum frost alpha
    float feather;       // softness of the freeze front, in amount units
    float rimWidth;      // depth of the bright crystallising edge, amount units
    float rimStrength;   // brightness of that edge
    float shadeStrength; // darkening under the ice, for pale themes
    vec4 tint;           // ice colour between the bright crystal lines
    vec4 rimColor;
    vec4 shade;          // colour of the darkening
};

layout(binding = 1) uniform sampler2D growth;

const float CRYSTAL_LEAD = 0.02; // crystal lines freeze a hair before the ice around them

void main() {
    vec3 m = texture(growth, qt_TexCoord0).rgb;
    float g = m.g;
    float f = max(feather, 0.001);
    float d = amount * (1.0 + f) - (m.r - g * CRYSTAL_LEAD);

    float frozen = smoothstep(0.0, f, d);
    float age = smoothstep(0.0, 0.45, d); // older ice is thicker

    float body = frozen * (0.015 + 0.15 * age);
    float cryst = frozen * g * (0.72 + 0.28 * age);
    float alpha = clamp(body + cryst - body * cryst, 0.0, 1.0) * intensity;

    // Pale themes: shadeStrength turns the crystals toward `shade` so they
    // read as darker lines, and lays a thin shade wash under the ice.
    float ink = clamp(shadeStrength, 0.0, 1.0);
    float hl = clamp(g * g * 0.9 + 0.08, 0.0, 1.0);
    vec3 ice = mix(mix(tint.rgb, vec3(1.0), hl), shade.rgb, ink * 0.8);
    vec4 c = vec4(ice * alpha, alpha);

    float rim = smoothstep(-f, 0.0, d) * (1.0 - smoothstep(0.0, max(rimWidth, 0.001), d));
    c += mix(rimColor, shade, ink * 0.6) * (rim * (0.06 + 0.94 * g) * rimStrength * 0.9);
    c += vec4(frozen * m.b * m.b * 0.95);
    c = clamp(c, 0.0, 1.0);

    float sa = clamp(frozen * shadeStrength * (0.10 + 0.18 * age), 0.0, 1.0);
    c += shade * sa * (1.0 - c.a);

    fragColor = clamp(c, 0.0, 1.0) * qt_Opacity;
}
