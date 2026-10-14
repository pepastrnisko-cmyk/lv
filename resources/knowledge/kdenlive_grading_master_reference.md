# Kdenlive and Color Grading Master Reference

(Bundled knowledge base supplied by the user, cleaned of build-script and console output.)

Part 0: Index and Authority

Authority rules

Color grading follows the Grading Guide (Part 1). K7 maps the guide onto Kdenlive and does not override it.

Kdenlive editing behavior follows K1 to K10. Where two sections seem to conflict, K1 and the Grading Guide win.

Every menu name, shortcut, parameter name, and value must be confirmed on screen before use.

Version facts live in K1 only. Other sections refer to K1 for version information.

Load by task

Any task: K1 (always loaded)

Color, grading, LUTs, scopes, shot matching, or "make color grading": Grading Guide, then K7. Load K3 or K8 only when masks or proxies are needed.

Timeline cuts, trims, moves, slip, slide, roll, ripple: K2

Layers, blend modes, masks, keys, transforms, picture-in-picture: K3

Effects, keyframes, transitions, speed, reverse, freeze: K4

Dialogue, music, levels, EQ, compression, loudness, sync, ducking: K5

Titles, lower thirds, logos, shapes, subtitles: K6

Import, bins, relinking, proxies, cache, archive: K8

Render, export, presets, delivery checks: K9 (run its pre-flight check first)

Shortcuts, layouts, workspaces, panel setup: K10

Always

Check the on-screen name before acting.

Save before risky operations. Undo once, then check the screen before doing anything else.

Ask before deleting, overwriting, rendering, changing project settings, or sending anything to a client or platform.

Part 0.1: Consistency Check Record

The following fixes were applied when this master document was assembled.

Version statements were repeated across K3, K4, K7, K8, K9, and K10. They now point to K1 only.

Shortcut defaults appeared in K2 and K10. They are kept in K10 only, and K2 refers to K10.

The old grading guide (background first, then clothing, then face) is superseded by the skin-anchored version in Part 1. Do not use the old version.

A LUT on its own is not a grade. This sentence is added to the Grading Guide.

White point and skin highlight limits are stated separately, so the frame's white point is not confused with the skin limit.

The typo "Underly saturated" is corrected to "Under-saturated."

No hard contradictions were found between sections. The issues were repetition and two missing sentences.

Items that must be confirmed on the user's installed build, not assumed: scope panel location, lift, gamma, and gain names, blend mode list, transform parameter names, transition alignment, speed keyframes, proxy and archive options, render presets, speech-to-text, and subtitle export formats.

Part 0.2: Version Note

The newest Kdenlive release identified at the time of writing is 26.08.0, released 31 August 2026. Maintenance releases after that date may exist. Check Help > About on the installed machine and confirm features against that version before use.

Part 1: Professional Color Grading Guide

 

Correction to the earlier guide

The earlier version put background first, then clothing, then face. That is a teaching order, not the usual professional one. Most colorists anchor on skin, because viewers judge a shot by its faces. They fix the primary balance, set the skin, then build everything else around it. Background work usually comes after the subject is right, because the background's job is to support the subject. You can still grade regions in the order you prefer, but this guide follows the professional sequence and explains where it differs.

Numbers in this guide, such as IRE targets and skin ranges, are common starting points. Working colorists adjust them by project, camera, and delivery spec. Treat them as references to check against your scopes, not fixed rules.

Part 1.1: What grading is

Grading has two layers:

Correction makes footage technically consistent: exposure, white balance, contrast, and matching between shots.

Grading gives the image a look that serves the story.

Professionals keep these separate in time. Correct first, then make creative choices. If you style a shot before correcting it, you end up hiding problems instead of solving them.

A LUT on its own is not a grade. A LUT is a starting point or a technical conversion, and the grade is the work you do after it.

Part 1.2: Signal basics

Luma is brightness. Chroma is color. Good grading treats them as separate controls.

IRE is the video-level unit: 0 is black, 100 is white in standard range. Scopes read in IRE or percent.

Bit depth sets the number of tonal steps per channel. 8-bit has 256 levels, 10-bit has 1024, and 12-bit or higher is common in cinema cameras. More bits mean fewer banding problems and more room to push the image.

Chroma subsampling (4:2:0, 4:2:2, 4:4:4) sets how much color detail is stored. 4:2:0 limits how far you can push color before artifacts show, especially on skin edges and saturated colors.

Gamma describes how encoded brightness maps to displayed brightness. Rec.709 displays are usually graded around gamma 2.4.

Color space is the range of colors a system can represent. Rec.709 is the standard for HD and web. DCI-P3 is common in cinema and Apple displays. Rec.2020 is the wide gamut used for HDR delivery.

Part 1.3: Log and raw

Log footage (S-Log3, V-Log, C-Log3, LogC, D-Log) stores more highlight and shadow detail by spreading tones flatly across the recorded range. Before conversion it looks washed out. This is intentional, and it is why an input transform comes first.

Raw files hold the sensor's data before any camera processing. Raw processing sets exposure, white balance, and color interpretation before the grade begins. Log and raw both give more latitude, but they require more care at the start.

Part 1.4: The scopes

Scopes are the professional's objective reference. Eyes adapt quickly and can be fooled by surrounding color, so watch the scopes first.

Waveform shows luminance across the frame, left to right. Use it for black, white, and midtone placement, and for spotting clipping (values pinned at 100 IRE) and crushing (values pinned at 0).

RGB parade shows red, green, and blue separately. Neutral surfaces should have equal channel levels. Color casts show up as one channel running higher or lower.

Vectorscope shows hue and saturation as a circle. Neutrals sit at the center. The distance from center is saturation, and the angle is hue. Skin tones fall along a diagonal line, the skin tone line or I-line, running from roughly the red-orange area toward yellow. This is the most useful reference for skin.

Histogram is a simpler tonal distribution view, useful for checking clipping.

Part 2: Environment and Monitoring

Part 2.1: Calibrate the display

A grade is only as trustworthy as the display it is judged on.

Use a hardware calibrator such as a Calman-compatible probe, an X-Rite i1 Pro, or a Datacolor Spyder, or have a calibration professional do it.

Typical SDR targets: D65 white point, gamma 2.4 (or the spec for your delivery), and luminance around 100 nits.

Recalibrate every few weeks for heavy use, and after changing hardware or room lighting.

Part 2.2: Control the room

Keep ambient light low and consistent. Bright light washes out the screen and changes how you perceive contrast.

Use neutral walls, ideally mid-gray or dark gray. Bright colored walls shift your perception.

Keep windows and light sources out of the screen's reflection.

Many colorists use a bias light, a dim neutral backlight behind the monitor, to reduce eye strain.

Part 2.3: Software setup (DaVinci Resolve as the example)

Set timeline resolution and frame rate to match the footage.

Use DaVinci YRGB Color Managed with a wide working space such as DaVinci Wide Gamut and DaVinci Intermediate, then set the output to match delivery (Rec.709 for standard HD and web, or the HDR pipeline for HDR).

Arrange the scopes so you can see the image and the scopes without moving your head.

Keep a reference still or a previous version visible for comparison.

Part 3: Conform and Normalize

Part 3.1: Identify the source

Know the camera, the recording format, the bit depth, the codec, and the chroma subsampling. Check whether the footage is log, Rec.709, HLG, PQ, or raw. The source determines everything in the steps below.

Part 3.2: Apply the input transform

Log footage: apply the manufacturer's technical transform (for example ARRI LogC to your working space, Sony S-Log3 to your working space, Canon C-Log to your working space). Resolve's built-in color management can handle many of these automatically.

Rec.709 footage: no transform is needed, but the image still needs correction.

Raw: set white balance, exposure, and color interpretation in the raw settings first.

Do not apply a creative LUT yet. The goal is a neutral, accurate base.

Part 3.3: Verify the transform

After the transform, the waveform should show detail across the range without clipping at either end. If the image looks badly wrong, check that the correct camera profile was used. Wrong profiles are one of the most common causes of a muddy start.

Part 3.4: Use reference charts

If a ColorChecker or gray card was shot on set, use it:

Set white balance by sampling the neutral patch.

Match multiple cameras by comparing their chart shots.

Use the chart's known values to check for camera-specific color shifts.

Part 3.5: Organize the timeline

Order clips by scene.

Mark problem shots: mixed light, flicker, focus issues, noise, skin problems, and continuity issues.

Identify hero shots, the ones that need the most attention.

Flag shots with VFX, since VFX may need a different grade approach or a separate deliverable.

Part 4: Scene Analysis

Before adjusting controls, study the scene. Experienced colorists often spend more time looking than adjusting.

Ask these questions:

What is the story moment? Tense, tender, calm, chaotic?

Where is the subject? Who or what must the viewer look at?

What are the light sources? Key light, fill, practicals (lamps, screens, windows), and whether they match in color temperature.

Is the light mixed? Window daylight with tungsten, or LED with fluorescent. Mixed light needs a decision about which source reads as "correct."

What is the mood? Write a few words.

Which regions matter? Skin, hero garment, eyes, background, props, and highlights.

Where is the problem? Exposure, color cast, noise, skin shifts, clipping.

Map the frame into regions: subject skin, hair, eyes, lips, clothing, props, background, foreground, and light sources. This map becomes your node structure.

Part 5: Primary Correction

Primary correction affects the whole frame. It sets the technical base for everything else. A typical primary order, with the controls in most grading systems:

Part 5.1: Set the black point (lift)

Find the darkest area that still holds detail.

Lower lift until that area sits just above black, usually a few IRE above 0 in SDR.

Avoid crushing: check that shadow detail remains visible in the waveform and in the image.

Compression smears deep shadows, so leave some margin.

Part 5.2: Set the white point (gain)

Find the brightest real highlight without a specular reflection, such as a white shirt, a bright sky, or a window edge.

Set it around 90 to 100 IRE, depending on the look. This is the frame's brightest real detail.

Skin highlights must stay below clipping, which may sit lower than the frame's white point. Check skin separately (Part 8.1).

Specular highlights (glints on metal, water, or glass) can sit higher. Avoid clipping on skin and fabric unless the look calls for it.

Part 5.3: Set the midtones (gamma)

Use faces and neutral surfaces to judge midtones.

Adjust gamma until the midtones feel natural. Faces should look neither too dark nor washed out.

Confirm on the waveform. Midtones usually cluster near the middle of the scale.

Part 5.4: Neutralize white balance

Find a neutral reference: a gray road, a white wall, a shirt collar, the chart.

Use the RGB parade to balance the channels until the neutral reads equal in red, green, and blue.

Alternatively, use the color wheels to move against the cast in the affected tonal range.

Confirm on the vectorscope. Neutrals should sit at the center.

For mixed light, decide which source is the reference. The subject's light is usually the reference, and the background can stay mixed.

Balance shadows and highlights separately when the lighting is mixed.

Part 5.5: Set contrast

Compare shadows, midtones, and highlights against each other.

Use the contrast or pivot control to add depth without crushing.

Use curves for finer control.

Part 5.6: Set global saturation

Start at neutral and change only after white balance and contrast are set.

Check the vectorscope. Colors should sit where expected.

Part 5.7: Check the primary

Toggle on and off, comparing before and after.

Watch in motion, not on a still frame.

Check at different playback speeds.

Confirm the scopes once more.

Part 6: Anchor on Skin

This is the key professional step that the earlier guide underplayed. Before secondaries, most colorists check the primary against the skin. If skin is off, everything else will look off too.

Part 6.1: Read the skin on the vectorscope

Skin should fall along the skin tone line.

Skin that sits far from the line is too red, too green, too magenta, or too yellow.

Skin that is tightly clustered looks natural. Skin that scatters across the vectorscope looks inconsistent.

Part 6.2: Read the skin on the RGB parade

Natural skin usually shows red as the highest channel, then green, then blue, though the exact spacing depends on lighting and skin tone.

An unusually high green channel points to a green cast. An unusually high blue channel can make skin look cold or gray.

Part 6.3: Adjust the primary to serve the skin

If skin looks correct but the background doesn't, leave skin alone and fix the background in a secondary.

If skin is off, correct it in the primary first when the cause is global, such as white balance.

Move to a secondary only when the problem is regional, such as one face lit differently from the rest of the frame.

Part 7: Secondary Correction

Secondary correction targets specific regions or colors. A professional sequence works from the subject outward.

Part 7.1: Tools

Qualifiers select pixels by hue, saturation, and luminance. They are precise when the target has a clear color range.

Power windows draw shapes (circle, rectangle, polygon, freeform). They isolate areas and can be tracked.

AI masks, such as Magic Mask in DaVinci Resolve or similar tools in other software, select people or objects. Always verify the edges.

Tracking follows masks and windows through the shot.

Blur, feather, and erode soften mask edges so changes blend.

Keyframes animate adjustments over time.

Part 7.2: Principles

Treat each secondary like a small primary. Check its scopes.

Keep changes subtle. If you can see the mask, it's usually too strong.

Toggle nodes often. If the change is obvious and distracting, reduce it.

View the matte on a black or white background to find halos and bleed.

Track through the whole shot. Check every frame where the subject turns, moves quickly, or passes behind something.

Part 7.3: Recommended order

This is a common professional sequence. You can adjust it to the shot.

Skin and face (the anchor)

Eyes

Hair

Lips

Hero clothing

Props and accessories

Background and environment

Foreground

Highlights and light sources

Shadows

The skin is graded early because the other regions are judged against it. The face is also checked again at the end, since later adjustments can shift how it reads.

Part 8: Region Details

Part 8.1: Skin and face

Goal: natural skin that matches the light in the scene and holds texture.

Selection:

Use a face power window or AI mask, tracked through the shot.

Add a skin qualifier to tighten the selection, targeting the skin's hue on the vectorscope.

Feather edges carefully to avoid visible boundaries at the jaw, hairline, and ears.

Check the matte on black to see whether hair, eyebrows, or lips are included.

Adjustments:

Hue: move the skin along the skin tone line toward the intended tone. Small moves only.

Saturation: adjust in small steps. Overly saturated skin looks sunburned. Under-saturated skin looks gray or ill.

Luminance: keep midtone skin in a natural band. Highlights on the forehead, nose, and cheekbones should stay below clipping.

Shadows: preserve detail in the eye sockets, under the nose, and under the chin.

Temperature: match the light. Warm light on the face can stay warm. Cool light should not be warmed unless the look requires it.

Texture: avoid heavy smoothing. Skin texture is part of realism.

Scope targets:

Vectorscope: skin clusters near the skin tone line.

Waveform: highlights below clipping, shadows showing detail.

RGB parade: natural channel relationships, not one channel dominating.

Pitfalls:

Waxy or plastic skin: usually from smoothing, clipped highlights, or excess saturation.

Orange or sunburned skin: usually from pushing hue or saturation too far.

Gray or dead skin: usually from over-desaturation or a cool shift.

Halos around the face: the mask is too hard or too large.

Face mismatched with neck and hands: grade the connected skin together, or match it deliberately.

Part 8.2: Eyes

Goal: bright, clear eyes without artificial whites.

Selection: small windows around each eye, tracked through blinks and movement. Use a qualifier for the whites if they need separating from skin.

Adjustments:

Whites: pull slightly below pure white and reduce any color cast. Real eye whites are rarely pure white.

Irises: a small saturation or hue lift can bring out color without overdoing it.

Brightness: lift slightly if the eyes sit in shadow.

Catchlights: protect them from clipping. They give the eyes life.

Pitfalls: eye whites that look neon or painted, masks that bleed onto skin, blown catchlights, and masks that lose track during blinks.

Part 8.3: Hair

Goal: color that reads clearly, texture that remains visible, and edges that don't look cut out.

Selection: use a hair-specific or AI mask if available. Otherwise use a window around the head with a luminance or hue qualifier. Hair edges are soft and often pick up background, so expect to refine them.

Adjustments:

Color: small hue and saturation shifts.

Highlights: pull specular highlights down to keep texture and avoid clipping.

Shadows: lift slightly to reveal depth.

Contrast: add a little to bring out texture on soft hair.

Pitfalls: hair that looks like a flat cutout, dark halos from background pickup, and clipped sheen.

Part 8.4: Lips

Goal: natural color with restrained saturation.

Selection: a small window or a qualifier on the lip hue, tracked through speech. Feather to blend with the skin.

Adjustments: lips usually need less saturation than expected. Adjust hue slightly toward red for warmth or toward magenta for coolness. Control highlights on glossy lips.

Pitfalls: lips that look neon, masks that bleed into skin, and lips that go gray.

Part 8.5: Hero clothing

Goal: garment color that serves the story and separates from the skin.

Selection: a garment qualifier on hue, saturation, and luminance, refined with a window if the qualifier catches skin or background. Track through folds and movement.

Adjustments:

Hue: small shifts to fit the palette or to separate the garment from skin. A red garment shifted slightly toward magenta separates from skin. Shifted toward orange, it moves closer to skin and can conflict with the face.

Saturation: reduce garments that are too loud. Increase only when a flat garment needs life.

Luminance: dark garments need shadow detail, light garments need highlight detail.

Contrast: add a little for texture, less on shiny fabric.

Scope targets: dark fabric shows detail without crushing. White fabric shows texture without clipping. Garment colors sit where you intend on the vectorscope, not overlapping the skin tone line unless intended.

Pitfalls: crushed black fabric, clipped white shirts, skin contamination from the qualifier, and dead, over-smoothed fabric.

Part 8.6: Props and accessories

Goal: objects that read clearly without competing with the face.

Notes: metal reflects light and needs highlight control to keep its sheen. Glass picks up color from the environment and may need its own correction. Colored props should fit the palette.

Pitfalls: metal that looks plastic, glasses that pick up unwanted color, and props that pull focus.

Part 8.7: Background and environment

Goal: a background that supports the subject without competing for attention.

Selection: the easiest reliable method is usually to mask the subject, then invert. Use a background qualifier when the background has a clear color range, such as sky or foliage. Refine the matte carefully at hair and shoulders.

Adjustments:

Luminance: a slight reduction often helps the subject separate. A 10 to 20 percent reduction is a common starting point.

Saturation: modest reduction, often 10 to 30 percent, to calm the environment. Heavy desaturation looks dead.

Hue: complementary shifts add contrast. Analogous shifts add harmony.

Temperature: a cool background can separate a warm subject. Check that the background's light direction and quality still match the subject's lighting.

Curves: hue-versus-saturation curves can target one background color.

Pitfalls: halos at the subject edge, hair leaking into the background mask, obvious cutout edges, and lighting that doesn't agree with the subject.

Part 8.8: Foreground

Foreground elements can be darkened or desaturated to push them back, or brightened to draw attention. Match their blur or focus to the mask. Feather edges to avoid a cutout look.

Part 8.9: Highlights and light sources

Goal: bright areas that keep their detail and sit in a natural color.

Selection: a luminance qualifier for the brightest areas, or windows around specific lamps, screens, or windows.

Adjustments: pull highlights down, match their color to the light's temperature, and roll off with a soft clip or highlight curve rather than letting them clip hard.

Pitfalls: clipped windows and lamps, and highlights colored wrong for their source.

Part 8.10: Shadows and noise

Goal: shadows with detail and controlled color.

Adjustments: lift shadows slightly to reveal detail. Shape shadow color to correct casts or to add a deliberate tone. Apply noise reduction before lifting, because lifting amplifies noise.

Pitfalls: noise amplified by lifting, crushed detail, and shadow casts visible only after grading.

Part 9: Shot Matching

Shot matching makes a scene feel continuous. Viewers notice mismatches even when they can't name them.

Part 9.1: Choose a reference

Pick the best-exposed, most representative shot in the scene. Many colorists use the hero shot. Make sure the reference is itself correct before matching against it.

Part 9.2: Match in this order

Exposure and contrast: black, white, and midtone placement on the waveform.

White balance: neutrals on the RGB parade and vectorscope.

Skin tones: the most sensitive element. Align the skin cluster on the vectorscope and compare faces side by side.

Secondary elements: garments, props, and environment where they should be consistent.

Part 9.3: Judge in motion

Play each cut through. Matching is decided by playback, not by still frames. Watch for jumps in brightness, color, or skin tone at cut points.

Part 9.4: Common mistakes

Matching to a flawed reference.

Matching only on scopes and not checking playback.

Matching too rigidly. Some variation is natural, and the story sometimes calls for it.

Part 10: Creative Look Development

Only after correction and matching should the creative look begin. The grade now expresses mood, genre, and story.

Part 10.1: Start from the story

Write a few words about the intended feeling: cold and isolating, warm and nostalgic, gritty, dreamy. Consider genre. Thrillers often lean cool with higher contrast. Romances often lean warm and soft. Period pieces often have muted palettes.

Part 10.2: Build a palette

Limit the dominant colors. Common approaches:

Teal and orange: cool shadows against warm skin or highlights.

Monochromatic: one hue family for unity.

Single accent: a mostly desaturated image with one color emphasized.

Complementary: opposing hues for tension.

Analogous: neighboring hues for harmony.

Part 10.3: Shape contrast

Lifted blacks feel soft or faded.

Crushed blacks feel heavy or graphic.

High contrast feels energetic. Low contrast feels gentle or dreamy.

Use curves to target specific tonal ranges.

Part 10.4: Control saturation

Global saturation is blunt. Hue-versus-saturation and saturation-versus-luminance curves give finer control. Desaturating shadows or highlights can add refinement. Selectively saturating one color creates emphasis.

Part 10.5: Texture and grain

Film grain adds character, but check it at delivery size. Grain that looks fine at full resolution may look heavy when scaled. Halation (soft glow around highlights) suits a filmic look. Vignettes should be subtle.

Part 10.6: LUTs

A LUT on its own is not a grade. It is a starting point or a technical conversion, and the grade is what you do after it. LUTs speed up exploration but should be tailored. A LUT built for one camera or lighting setup may not suit your footage. Apply it, then adjust the result, and check skin on the vectorscope and waveform afterwards, since LUTs often shift skin.

Part 10.7: Versions

Save versions as you go and name them clearly, such as "v03 warmer skin" or "v05 lower contrast." Clients often ask to compare options.

Part 11: Review and Delivery

Part 11.1: Review on multiple displays

Check on the calibrated reference monitor, a consumer TV, a laptop, and a phone if possible. Problems invisible on one display may be obvious on another.

Part 11.2: Check the delivery format

Grade in the working space but review in the output space. For HDR, verify on an HDR display and check highlight roll-off and clipping.

Part 11.3: Artifacts

Banding in skies and dark gradients: add grain or dither, or reduce steep curve adjustments.

Posterization from heavy adjustments on low bit-depth footage.

Crushed detail in shadows.

Noise exposed by lifting.

Halos from secondary masks.

Bleed from masks picking up adjacent areas.

Part 11.4: Legal levels

For broadcast, use the broadcast-safe or legal range tools to confirm luminance and chroma are within limits. Check the waveform for values above 100 or below 0 IRE.

Part 11.5: Continuity

Play the full sequence. Watch for flicker, sudden shifts, and drift in skin tones at every cut.

Part 11.6: Export and verify

Render the final file and check the exported version. Compression changes how a grade looks, so review the delivered file on the intended playback device.

Part 12: Troubleshooting

Problem Likely cause Fix Skin looks orange Hue or saturation pushed too far Move back along the skin tone line, reduce saturation Skin looks green or gray Green cast or over-desaturation Correct white balance, restore warmth carefully Skin looks waxy Smoothing or clipped highlights Lower highlights, restore texture Halo around subject Mask too hard or too large Feather, erode, refine matte Background looks dead Over-desaturation Restore saturation, shift hue instead Clothing crushed Shadows too dark Lift shadows within the garment White shirt clipped Highlights too high Pull highlights down Scene doesn't match Unmatched white balance or contrast Match to reference using scopes and playback Grade flickers Unstable mask or keyframes Track more carefully, check keyframe timing Banding in sky Low bit depth or steep curves Add grain or dither, soften curve Shadow noise after lifting Noise amplified Denoise before lifting Eyes look artificial Whites too bright Lower brightness and saturation of whites Hair looks cut out Hard hair mask Use hair-specific mask, soften edges Different on phone Display calibration or color space Review on multiple displays, verify output transform

Part 13: Checklist

Environment

[ ] Display calibrated

[ ] Room dim and neutral

[ ] Scopes visible

[ ] Color management configured

Conform

[ ] Source format identified

[ ] Correct input transform applied

[ ] Reference chart checked

[ ] Timeline organized by scene

[ ] Problem and hero shots marked

Analysis

[ ] Story and mood defined

[ ] Light sources and temperature assessed

[ ] Regions mapped

Primary

[ ] Black point set without crushing

[ ] White point set without clipping

[ ] Midtones natural

[ ] White balance neutral

[ ] Contrast and saturation set

[ ] Checked in motion

Skin anchor

[ ] Skin on the skin tone line

[ ] Skin balanced on the RGB parade

Secondaries

[ ] Skin and face graded and tracked

[ ] Eyes, hair, and lips adjusted

[ ] Hero clothing controlled

[ ] Props controlled

[ ] Background graded with clean matte

[ ] Highlights and shadows handled

[ ] Final face check done

Matching

[ ] Reference shot chosen

[ ] Exposure, white balance, and skin matched

[ ] Sequence played through each cut

Look

[ ] Palette chosen

[ ] Contrast and saturation shaped

[ ] Grain and texture used sparingly

[ ] Versions saved

Delivery

[ ] Reviewed on multiple displays

[ ] Artifacts and legal levels checked

[ ] Continuity verified

[ ] Final export checked

Part 14: Practice Exercises

Scope reading: take ten unrelated clips and correct only the primary. Don't add any look. Compare them on the waveform and vectorscope.

Skin matching: take two shots of the same person under different light. Match the skin using only the vectorscope and the RGB parade, then check by eye.

Mask discipline: track a face mask through a clip with head turns. Check the matte on black and white. Remove any halo.

Restraint: grade a scene with a strong look, then reduce every control by half. Compare the two on playback.

Reference study: pick a film you admire. Screenshot five frames and try to recreate the skin and background relationship, without copying the look.

Closing notes

Professional grading is a sequence: correct the image, anchor on skin, shape the regions, match the scene, then build the look. The order matters because each step relies on the one before. Trust the scopes to set the base, and trust your eyes once the base is correct. Check the grade in motion, on the displays where people will actually watch it, and step away for a while before final decisions.

K1: Core (always loaded)

 

ROLE

You are a professional video editor working in Kdenlive through screen control. You see screenshots and act with mouse and keyboard. You edit with intent: every cut, transition, and effect should serve the story, the pacing, or a stated technical need.

VERSION RULE

This reference describes general Kdenlive behavior. Menu names, shortcut keys, and effect names vary by version. Before using any name or shortcut, confirm it on screen. If it differs, use the on-screen name and note the difference. Check the Help menu, or Settings > Configure Shortcuts, when unsure.

Newest release identified at the time of writing: Kdenlive 26.08.0, released 31 August 2026. Maintenance releases after that date may exist. Check Help > About on the installed machine. Other sections refer to this note for version information.

Release notes for 26.04 added a Disable Timeline Effects option in the timeline's hamburger menu, a Euclid Eraser transition, a Heatmap effect, and effect and transition workflow improvements. Release 26.04.3 improved the Rectangular Alpha Mask and Rotoscoping effects. Check whether these exist and behave as described in the installed version.

WORKING RULES

Screenshot before and after each action group. Don't chain many clicks without checking the result.

Enter exact numbers in value fields. Record every value set.

One change at a time, then verify on the monitor and timeline.

Save the project (Ctrl+S) before risky operations, and save versions (File > Save As with a version suffix) before major changes.

Undo (Ctrl+Z) if a change goes wrong, and confirm it in a screenshot.

Ask before deleting media or clips, overwriting files, removing tracks with content, rendering over an existing file, or changing project settings that affect existing material (frame rate, resolution).

Label clips, tracks, and effects so the timeline stays readable.

CORE CONCEPTS

Project: a .kdenlive file (XML) that stores references to media, the timeline layout, effects, keyframes, and settings. Media stays where it is on disk. Moving or renaming source files breaks links.

Bin (Project Bin): the library of clips, sequences, folders, and proxies. Clips in the bin are references, not copies.

Clip: a piece of media in the bin. Clip properties include in and out points, duration, frame rate, and audio and video streams.

Timeline: the editing surface. It holds tracks, which hold clips placed at timeline positions. Video tracks stack upward (V1 at the bottom, higher tracks composite over lower ones). Audio tracks are separate.

Monitors: the Clip Monitor (source, for setting in and out on a bin clip) and the Project Monitor (program, showing the timeline at the playhead).

Playhead: the current frame of the timeline. Most operations act at it.

Frame rate and resolution: project settings set the timeline. Clips with different frame rates or sizes are conformed on the timeline.

Engine: Kdenlive runs on the MLT framework and FFmpeg for decoding and rendering. Codec and format support depends on the installed FFmpeg.

ANATOMY OF AN EDIT

Source in and out: the used portion of a clip.

Timeline in and out: the placed portion on the timeline.

Overwrite places a clip on the timeline and replaces what was there. Insert pushes existing clips later to make room. Use insert when no material should be lost, and overwrite when the timeline length must stay fixed.

Sync: audio and video from one source are linked so moves stay together. Unlink when you need to edit them separately.

WORKFLOW (default order)

Setup: project settings, frame rate, resolution, audio sample rate.

Ingest: import media into organized bin folders. Check codecs and frame rates.

Proxies, if footage is heavy: generate or enable proxies before editing, then check that the proxy and original match (K8).

Assembly: place selects in sequence order.

Rough cut: arrange the story and remove what doesn't serve it.

Fine cut: refine cut points, pacing, and sync. Use J, K, L and frame stepping (K2, K10).

Sound: dialogue cleanup, levels, music, and mix (K5).

Color: hand off to the grading reference and K7.

Effects, titles, and graphics (K3, K4, K6).

Review: play the full timeline, check continuity and sync.

Render: run the pre-flight check, then choose the delivery preset (K9).

STOP AND ASK WHEN

Media is offline or links are broken.

A change would ripple through many clips unexpectedly.

Frame rate or resolution would change after clips are placed.

A render would overwrite an existing file.

The edit changes the meaning of the material, such as a cut that reorders events, or audio that alters what someone said.

A requested effect is missing in the installed version.

FAILURE HANDLING

Control not found: search the menus once, then ask.

Playback stutters: check proxies, playback quality, and cache, then report what you see rather than guessing.

Unexpected result: undo, check track targeting and edit mode, then try again.

Screen doesn't match expectations: take a fresh screenshot and report.

Never claim a result you have not seen on screen.

REFERENCE SECTIONS

Load the sections below only when the task needs them:

K2: Timeline editing and trimming

K3: Tracks, compositing, and transforms

K4: Effects, keyframes, and transitions

K5: Audio

K6: Titles and graphics

K7: Color tools (links to the grading reference)

K8: Media management and proxies

K9: Rendering and delivery

K10: Keyboard shortcuts and workspace

K2: Timeline Editing and Trimming

 

Load when editing the timeline.

PURPOSE

Edits are where story and rhythm are decided. This section covers how to select, cut, trim, move, and rearrange clips on the timeline precisely. Choose the tool by what the edit needs: keep the length, change the length, or move content without changing its timing.

VERIFY ON SCREEN

Tool names, default shortcuts, modifier keys (Shift, Ctrl, Alt), and the Timeline toolbar layout can change between versions. Shortcut defaults are kept in K10. Check each one on screen before use.

TIMELINE TOOLS

Selection tool: select, move, and trim clips. The default tool.

Razor (cut) tool: splits a clip at a point. Cuts only the clip under the pointer, on the chosen track or tracks.

Spacer tool: removes or inserts a gap and moves everything after it. Use it to close or open space without touching clip content.

Trim tools (verify names on screen): ripple, rolling, slip, and slide, each covered below.

Snapping: a toggle that makes clips and the playhead align to edges, markers, and the playhead. Turn it off for fine positioning, on for alignment. Confirm its shortcut in K10.

TRIM TYPES

Ripple trim: move one edit point and shift everything after it on the same track. The sequence length changes. Use it to tighten pacing.

Roll trim: move the cut between two adjacent clips. Their total length stays the same, and nothing else moves. Use it to adjust where a cut lands without changing timing downstream.

Slip: change which part of the source a clip shows, without changing its position or duration on the timeline. Use it to change a shot's content while keeping its timing.

Slide: move a clip between two neighbours. The neighbours change length to compensate, and nothing else moves. Use it to reposition a clip while keeping the sequence length.

Overwrite trim: trimming without moving later clips. Useful when the track's timing must stay fixed.

EDIT MODES AND PLACEMENT

Overwrite places material on the timeline and replaces what was there. Use it when the total length must stay fixed, for example a locked music bed or a fixed broadcast slot.

Insert places material and pushes existing clips later on the track. Use it when no footage should be lost.

Three-point and four-point editing: setting in and out points on the Clip Monitor (source) and/or the Project Monitor (record) to define what goes where. Confirm which points Kdenlive uses for each mode on screen.

Drag-and-drop from the bin or Clip Monitor: placement depends on where you drop and on track targeting. Check the placement preview.

SOURCE AND TIMELINE POINTS

Mark in and out on the Clip Monitor for the source portion.

Mark in and out on the Project Monitor for the timeline region.

Clear in and out points when they are no longer needed, since stale marks cause wrong placements.

Check a clip's properties to confirm its exact in and out values before placing it.

PRECISION TOOLS

Frame stepping: move one frame at a time with the arrow keys. Behavior depends on which panel has focus, so confirm on screen.

Timecode entry: type a timecode to jump the playhead to an exact frame.

Zoom: zoom the timeline to see frame-level detail before a precise trim.

Track targeting: the active track or tracks receive the edit. Check which tracks are targeted before every insert or overwrite. Targeting is highlighted in the track header.

Track locking: lock tracks you must not change, such as a locked music track or a finished section.

MULTI-SELECT AND GROUPING

Select several clips with a rubber band or Ctrl or Shift click. Confirm the behavior on screen.

Group clips that must move together, such as a video clip and its matching audio when they are not linked. Ungroup before separating.

Linked clips: video and audio from one source move as a pair. Unlink only when you need to edit them separately, then relink if sync must be kept.

MARKERS AND GUIDES

Markers label moments in the timeline, such as cue points, beats, and notes. They help with navigation and with music-cut timing.

Guides are visual alignment lines. They don't affect the render.

Use markers to set cut points against audio beats or dialogue. Check on screen whether a marker belongs to the timeline or to a clip.

PRACTICAL EDITING RULES

Cut on motion or on the action, not before it. Leave a few frames of handles for transitions and corrections.

Keep J and L cuts (audio leading or trailing the picture) purposeful. They carry dialogue across scenes and pace the story.

Match cut lengths to the story. A cut that shows nothing new is a wasted frame.

Reserve ripple edits for the final sequence, and check the knock-on effects on sync, music, and effects before committing.

Don't leave unintended gaps. Check the timeline for gaps and overlaps before rendering.

STOP AND ASK WHEN

A ripple or insert would move clips that have synced audio, music, or VFX the user hasn't reviewed.

A trim would cut into material the user hasn't approved.

The edit changes the sense of dialogue or the order of events.

The target track is unclear, or several tracks are targeted.

FAILURE HANDLING

Clip jumped or moved unexpectedly: undo once, check track targeting and the active tool, then try again.

Gap or overlap appeared: check snapping and the edit mode, then report what you see before fixing.

Tool or mode not found: search the Timeline toolbar and menus once, then ask.

Playhead or trim point not visible: zoom the timeline and take a fresh screenshot.

RELATED SECTIONS

K3: tracks, compositing, and transforms

K4: effects, keyframes, and transitions

K5: audio and sync

K10: shortcuts and workspace

Part 0.2: Version Note

K2: Timeline Editing and Trimming

versions. Shortcut defaults are kept in K10. Check each one on screen before use.
  K3: Tracks, Compositing, and Transforms

 

Load when layering, masking, keying, or positioning picture.

PURPOSE

Layering and positioning decide what the viewer sees and where. This section covers how tracks stack, how clips combine with the layers below them, how to mask and key, and how to place, scale, crop, and move picture precisely.

VERIFY ON SCREEN

Track header buttons, blend mode names, transition names, the Transform effect's parameter names, and the chroma key and alpha mask effect names can differ by version. Version notes are in K1. Confirm each name on screen before use.

TRACK TYPES AND STACKING

Video tracks stack upward. V1 is the lowest. Higher video tracks cover lower ones unless their clips are transparent, masked, or blended.

Audio tracks are separate and do not stack visually.

The Project Monitor shows the composite of all visible tracks at the playhead. What the viewer sees is the result of the whole stack, not a single track.

Stacking order is the layer order. To change it, move the track's clips or the track itself on screen. Verify the order after each move in the Project Monitor.

TRACK CONTROLS (check header buttons on screen)

Target: the track that receives inserts and overwrites. Check it before every placement.

Lock: prevents edits to a track. Lock finished or approved tracks.

Mute (audio) and hide (video): hide a video track to check what is below it. Hidden tracks don't render in the Project Monitor.

Track height: change for visibility, not for editing precision.

Track naming: rename tracks to their role, such as Titles, Graphics, Background, or Key, so the stack is readable.

PLACING CLIPS ON SEPARATE TRACKS

Move a clip up or down a track by dragging vertically. Check the target and the stacking result on the Project Monitor.

Keep related items on one track when they must move together, such as a picture and its mask, or group them.

COMPOSITING: HOW A CLIP COMBINES WITH THE LAYER BENEATH

Opacity reduces how much a clip shows. Set it with the clip's opacity control or an opacity-related effect, typed as an exact percentage. Check the exact control name on screen.

Blend modes change how the clip combines with the layers below. Common modes include Normal, Multiply, Screen, Overlay, Add, and Difference. Confirm the list in the installed version, since names and availability vary. Compare against the source with the blend off.

Composite transition controls how one track's picture blends with the one below it over a region. Check the exact transition name and whether it applies per clip or per track on screen.

Alpha and transparency: transparent areas let lower tracks show through. PNG and some video codecs carry alpha. Check the file's alpha on screen before relying on it.

MASKING AND KEYING

Alpha mask uses one clip's luminance or alpha to reveal or hide another clip. Check the mask's invert and feather controls on screen.

Rectangular alpha mask is a shape mask for rectangle-based reveals and split screens. Version 26.04.3 improved it, so check its controls on screen.

Rotoscoping draws shape masks over a clip, often with keyframes. Use it for moving subjects. Each point needs checking through motion, and the mask edge needs feathering to avoid visible outlines.

Chroma key (green or blue screen) removes a color range to reveal the layer below. Set the key color with the color picker, then adjust tolerance, softness, and spill suppression. Check the matte on a solid background, and watch for green fringing on hair and edges.

Luma key removes a brightness range. Useful for shapes on a black or white background. Check which luminance range the control keys.

SAFE AREAS AND FRAMING

Turn on safe-area guides (check the monitor overlay options on screen) before placing titles and key subjects.

Title-safe is inside the inner frame. Action-safe is the outer frame. Keep text and faces inside these areas for broadcast.

Keep faces off the edges unless the shot calls for it. Check framing at the final render size, not only at the timeline size.

TRANSFORMS: POSITION, SCALE, ROTATION, CROP

Transform or affine effect is the main tool for moving, scaling, and rotating a clip. Its parameters typically include position (X and Y), scale (uniform or per axis), rotation, and anchor or center. Confirm the names on screen.

Uniform scale keeps the aspect ratio. Use it for most resizing to avoid distortion.

Non-uniform scale distorts the image. Use only when the look is intentional or for a deliberate stretch.

Crop removes edges of the picture. Crop controls are separate from scale. Check on screen whether crop changes the frame or the clip's visible area.

Position in pixels or percent: check which unit the control uses, and enter exact values from the project's resolution.

Anchor point is where scale and rotation pivot. Move the anchor when a clip should scale from a corner or from a face, not from center.

PICTURE-IN-PICTURE AND SPLIT SCREEN

Picture-in-picture: scale a clip down, position it, and place it on a higher track than the full-frame clip. Add a border or shadow only if the design calls for it, using the effects available in the installed version.

Split screen: use rectangular or shape masks, or crop and position two clips in a layout. Match both halves for exposure and color before compositing.

Pan and zoom (Ken Burns): animate scale and position with keyframes across a still image or clip. Keep the motion slow and eased unless the pacing calls for speed.

KEYFRAMES FOR POSITION AND OPACITY

Set keyframes on the parameter, move the playhead, and change the value. Confirm the interpolation (linear, smooth, hold) on screen. Smooth is the default choice for moves.

Check the motion in playback, not only on the keyframes. Scrub through the transition and watch for jumps.

PRACTICAL RULES

Composite on a neutral background first, then check edges against the final background color.

Check each layer with its neighbours hidden and shown, to find unexpected transparency.

Verify that masks and keys are applied to the right clip, not to the track.

Check that a title or graphic stays readable on the brightest and darkest frames of the scene.

STOP AND ASK WHEN

A composite would hide content the user has not approved.

A key or mask fails on more than a few frames, or leaves visible fringe that feathering doesn't clear.

A transform would distort the picture beyond the intended aspect ratio.

A layer order change would affect graphics or titles the user has not reviewed.

Source alpha is unclear and the composite depends on it.

FAILURE HANDLING

Layer missing from the Project Monitor: check track visibility, opacity, and whether the clip is on the targeted track.

Edge fringe on a key: adjust spill suppression and tolerance, then check the matte on a solid background.

Position jumps during playback: check keyframe interpolation and whether a parameter is set on the clip or on a parent effect.

Control not found: search the effect library and the clip's effect stack once, then ask.

RELATED SECTIONS

K2: timeline editing and trimming

K4: effects, keyframes, and transitions

K7: color tools (matching layers before compositing)   K4: Effects, Keyframes, and Transitions

 

Load when adding effects, animating values, joining shots, or changing speed.

PURPOSE

Effects change how a clip looks or sounds. Keyframes change those settings over time. Transitions join two clips across a cut. Speed changes how fast a clip plays. Each of these can make an edit feel polished or amateur, so use them with restraint and with a reason.

VERIFY ON SCREEN

Effect and transition names, the Effect Stack layout, keyframe controls, and the speed tool's location can change between versions. Version notes, including the 26.04 changes, are in K1. Check whether an item exists in the installed version before using it.

WHERE EFFECTS LIVE

Clip effects apply to one clip and travel with it when it moves or is trimmed.

Track effects apply to everything on a track. Use them for a shared look across a track. Check whether the track effect applies before or after clip effects on screen.

Master effects apply to the whole output. Use them sparingly, and make sure they don't conflict with clip effects.

Bin clip effects apply to the source clip. Changes may not carry to instances already placed on the timeline, so check each instance.

EFFECT STACK

Each clip has an ordered stack of effects, and the order changes the result. Blur before color is not the same as color before blur. Sharpen before scale can produce different edges than sharpen after scale.

General order that works in most edits: input and technical corrections first (such as a log transform or a stabilizer), then geometry (crop and transform), then color (see K7), then creative effects (blur, glow, grain, overlays), and last any output-level effects.

Reorder effects by dragging in the stack. Verify the result on the monitor after each move.

Disable an effect with its on or off toggle to check its effect without deleting it. Delete only when the effect is no longer needed.

Rename effects or add notes so the stack is readable later.

Copy and paste effects between clips to match a look. Check each pasted effect's keyframes and parameters, because paste can carry values that don't suit the new clip.

Save effect stacks as presets when a look must be reused. Name presets by purpose, such as "Soft halation 2 percent" or "Interview stabilize standard."

COMMON EFFECT CATEGORIES (check the library on screen)

Color and correction: color wheels, curves, levels, white balance, LUT loading. Covered in K7.

Blur and sharpen: gaussian blur, sharpen, unsharp. Keep sharpening small, and check for halos at edges.

Stabilization removes camera shake. Check whether the installed version's stabilizer is available. Stabilizing adds crop, so check the frame edges after stabilizing.

Noise and grain: denoise and film grain. Denoise before lifting shadows, as covered in the grading guide.

Distortion and transform: transform (see K3), lens correction if available, and warp effects. Use lens correction only when it matches the lens, and don't stretch footage.

Keying and masking: chroma key, luma key, alpha mask, and rotoscoping (see K3).

Speed: see the speed section below.

Overlay and creative: light leaks, vignettes, glow, and the Heatmap effect. Use creative overlays only if the story supports them.

Audio effects: covered in K5.

KEYFRAMES

A keyframe stores a value at a moment. Between two keyframes, the software interpolates. Check the interpolation mode on screen. Linear moves at a constant rate and can look mechanical. Smooth (ease) starts and stops gently and is the default for most motion. Hold keeps a value until the next keyframe, which suits switches and cuts.

Set a keyframe by changing a parameter at a playhead position, or by clicking the keyframe button next to the parameter. Confirm on screen which method the installed version uses.

Move keyframes by dragging, and adjust timing precisely by typing a frame number. Keyframes can be copied and pasted between parameters.

Use the keyframe curve or graph view, if available, to shape ease-in and ease-out. Check the motion in playback, not only on the graph.

Keep keyframe counts low. Many keyframes on one parameter suggest the motion should be simplified.

Remove a keyframe when the animation is no longer needed. Removing all keyframes returns the parameter to a single value, so check the value afterwards.

Keyframes live on the clip. When a clip is trimmed, keyframes move with its source, so check after trimming whether the timing still works.

TRANSITIONS

Transitions join two clips across an edit point. They need overlap or handles (extra source frames) on both sides of the cut. Without handles, the transition can't be made or will be shortened.

Common transitions include dissolve (cross-dissolve), wipes, slides, and push. Check the transition library on screen for names and parameters. The Euclid Eraser transition arrived in 26.04.

Transition length: short transitions (a few frames) read as clean cuts. Long dissolves read as time passing or as dreamy. Match the length to the story and pacing.

Centered transitions straddle the cut point. Transitions from one edge start at the edit point. Check which one the installed version uses before adjusting cut points.

Transitions on a track (between clips on one track) and between tracks (compositing) behave differently. Keep them separate in your mind.

Use a dip-to-black or fade-to-black when the story needs a clear break. Use a dissolve for continuity and a hard cut for energy.

Avoid flashy transitions for their own sake. Most professional editing uses cuts, with transitions reserved for real changes in time or place.

SPEED, REVERSE, AND FREEZE

Change speed sets playback speed as a percentage. Check the speed tool on screen. Changing speed changes the clip's duration on the timeline. Slow action when it needs weight, and speed up to tighten pacing.

Reverse plays the clip backward. Check that the action still makes sense and that no text, such as signs, reads wrong.

Freeze frame holds one frame for a set duration. Use it for emphasis or as a still moment before a title or transition.

Speed ramps change speed over time with keyframes, if the installed version supports speed keyframes. Otherwise use segments of different speeds with cuts.

Frame interpolation smooths slow motion by generating in-between frames. It can produce artifacts on fast motion, so check each shot. Use it only when the result looks clean.

Audio pitch: check whether a speed change also changes audio pitch in the installed version, and fix it with the audio tools in K5 if needed.

DISABLING EFFECTS AND CHECKING

Disable Timeline Effects (in 26.04 and later, from the timeline's hamburger menu): temporarily turns off effects across the timeline for a clean view. Turn it back on before rendering, and confirm the state on screen.

Compare effects on and off to check whether each one serves the edit.

Watch for effects that render slowly. Check playback quality and proxies (K8) if the preview stutters.

PRACTICAL RULES

Start with the story. Every effect should have a reason.

Restraint is the default. If an effect is noticeable, ask whether it's needed.

Keep transitions consistent across a sequence unless the story calls for change.

Avoid stacking many effects on one clip without checking each step.

Check the frame edges after any transform, blur, or stabilizer.

For a complex edit, keep a list of applied effects so you can review the full stack before rendering.

STOP AND ASK WHEN

An effect or transition changes the meaning of the footage or the sequence.

A speed change or reverse alters a shot the user hasn't approved.

A keyframed effect would fail on frames the user hasn't reviewed.

A transition requires handles that the clips don't have.

A creative effect is outside the agreed look.

FAILURE HANDLING

Effect not found: search the effect library once, then ask.

Effect has no visible result: check that it is enabled, sits in the correct stack position, and has a non-zero value.

Keyframes don't play as expected: check the interpolation mode and whether the parameter has keyframes at the correct frames.

Transition won't apply: check for handles on both clips and whether the transition length exceeds the available overlap.

Preview stutters after adding effects: check playback settings and proxies, then report what you see.

RELATED SECTIONS

K2: timeline editing and trimming

K3: tracks, compositing, and transforms

K5: audio effects and sync

K7: color effects and LUTs

K8: proxies and playback performance   K5: Audio

 

Load when editing dialogue, music, levels, sync, or the mix.

PURPOSE

Audio carries more of the viewer's experience than most people notice. Clear dialogue, consistent levels, and a music bed that supports the picture make an edit feel professional. Bad audio makes viewers leave even when the picture is good. This section covers how to clean, balance, shape, and sync sound, and how to check the final mix against delivery loudness standards.

VERIFY ON SCREEN

Audio mixer layout, effect names, meter scales, loudness-meter availability, and audio tool shortcuts can differ by version. Confirm each one on screen before using it. If a loudness meter or a specific effect is missing, say so and use the closest available tool.

AUDIO BASICS

Sample rate is how many times per second audio is measured. 48 kHz is the standard for video. Match the project's audio sample rate to the footage where possible, to avoid conversion.

Bit depth: 16-bit is common for delivery, 24-bit for recording and editing. Work at the highest depth the project supports.

Decibels (dB) are the unit for level. 0 dBFS is full scale on digital audio, so every level is negative. Mixing usually peaks around -6 to -12 dBFS for headroom.

Peak versus average: peak meters show the highest instant value. Average (RMS-style) meters show perceived loudness better. Watch both.

Clipping: digital audio above 0 dBFS distorts permanently. Keep peaks below it.

True peak is the peak value after reconstruction. Delivery specs often require true peak below about -1 dBTP to avoid distortion on playback.

Loudness (LUFS) measures perceived loudness over time. Common references: about -23 LUFS for EBU R128 broadcast in Europe, about -24 LUFS for ATSC A/85 in the US, and about -14 to -16 LUFS for many streaming and online platforms. Check the target your delivery requires.

AUDIO TRACKS AND ROUTING

Audio tracks are separate from video tracks and do not stack visually.

Each audio track has level, pan, mute, solo, and record-arm controls (verify on screen). Mute and solo help isolate a track while mixing.

Linked clips move together. Unlink to edit audio alone.

Master bus is the final output. Check the master meter when you reach the mix.

Mono, stereo, and multichannel: confirm how the source was recorded. A mono source placed in a stereo track may play centered or on one side. Check on screen and in headphones.

AUDIO MIXER

Open the audio mixer panel to see levels, meters, and effects for every track at once. Use it for balancing, not for fine cutting.

Fader or level control: set in decibels, typed as exact values where possible.

Meters: watch the peaks during playback, not only on a still frame.

Keep the master near the delivery target. Adjust individual tracks before adjusting the master.

LEVELS AND KEYFRAMES

Set clip level with the clip's volume control or a volume effect. Keyframe the level to duck music under dialogue or to fade a shot.

Fades: short fades (a few frames to a few tenths of a second) remove clicks at cuts. Longer fades (a second or more) shape music or a scene's end. Check each fade's shape on screen, linear or logarithmic if offered.

Clip gain adjusts the source before effects. Use it to fix a quiet or loud take before compression or EQ.

NORMALIZATION

Peak normalization sets the highest peak to a target. It is simple, but it doesn't match perceived loudness across clips.

Loudness normalization matches perceived loudness, and is the better choice for dialogue across clips. Use it per clip when source levels vary, then balance by ear and by meter.

Normalize before EQ and compression, so the tools work on a known level.

EQ (EQUALIZATION)

Parametric EQ adjusts frequency bands, with control over center frequency, gain, and width. Confirm the available bands on screen.

High-pass filter removes rumble and low noise below speech, typically around 80 to 120 Hz for dialogue. Check that it doesn't thin the voice.

Low shelf and high shelf adjust warmth or air. Small moves only.

Cut harshness: a narrow cut in the 2 to 5 kHz region can reduce harshness. Sibilance (esses) lives around 4 to 8 kHz, so move carefully there.

Boost presence: a gentle lift around 2 to 5 kHz can help dialogue cut through music. Small gains only.

Always compare EQ on and off, and listen on headphones and speakers.

COMPRESSION AND LIMITING

Compressor reduces dynamic range, bringing loud and quiet parts closer in level. Controls: threshold, ratio, attack, release, and makeup gain. Dialogue often uses a ratio of about 2:1 to 4:1 with moderate attack and release. Check the gain reduction meter.

Limiter stops peaks from exceeding a ceiling. Put a limiter on the master to protect the delivery peak. Set the ceiling to match the delivery spec (for example -1 dBTP).

Over-compression sounds pumping or flat. Reduce the ratio if breathing or pumping is audible.

Order matters: normalize, then EQ, then compress, then limit. Keep the limiter last.

NOISE REDUCTION

Noise reduction removes constant background hiss, hum, or room tone. Use the noise profile from a quiet section of the same recording.

Keep settings light. Heavy reduction produces a watery, artifact-filled sound.

Hum (50 or 60 Hz and harmonics): a notch filter can remove it. Use the mains frequency for your region.

Denoise the clip before adding effects that amplify noise.

DUCKING

Ducking lowers music when dialogue plays. Options are a sidechain compressor keyed to the dialogue track, or manual keyframes on the music track.

Keep the music audible at a reduced level rather than muting it fully. A drop of around 6 to 12 dB under dialogue is a common starting point.

Ease the transitions in and out. Abrupt ducking sounds unnatural.

SYNC

Video and audio sync is set when clips are placed. Check sync at the start, middle, and end of long clips, especially with separate recorders.

Clap or slate: a sharp transient at the start of a take gives a visible waveform spike to match against the picture.

Drift: if sync holds at the start but drifts later, the camera and recorder clocks differ. Check each long take and resync if needed.

Resample at the placement stage, not during the mix, to avoid repeated conversion.

J AND L CUTS

A J cut has audio start before the picture. An L cut has audio continue after the picture ends. Both carry dialogue across cuts and help the story flow.

Make them by unlinking the clips, then moving the audio alone. Relink afterward only if sync remains correct.

MUSIC

Choose music that supports the story. Check that the track's rights cover the intended use and distribution.

Cut music to structure: align cuts and beats with markers.

Fade music in and out. Avoid sudden endings that cut a phrase unless the moment calls for it.

SPEECH-TO-TEXT AND SUBTITLES

Some versions offer automatic speech-to-text for subtitles. Verify whether the installed version has this feature, then check every generated line against the audio. Automatic captions often mishear names and terms.

Keep subtitle timing aligned to speech, not to the picture alone.

MIXING ORDER

Clean dialogue: denoise, high-pass, gain.

Balance dialogue levels across clips: loudness normalization or manual.

EQ and compression on dialogue.

Place music and ducking under dialogue.

Sound effects and ambience at the right level.

Master bus: limiter and final loudness check.

FINAL CHECK

Listen on headphones, laptop speakers, and a phone or TV if possible.

Check loudness against the delivery target with a meter, or confirm the export settings if the target is set there.

Check the true peak on the master for clipping.

Play the full sequence and check that dialogue is clear at every cut.

STOP AND ASK WHEN

Dialogue would change meaning through cuts, trims, or edits.

Noise reduction or EQ changes a voice so it no longer sounds like the speaker.

Music rights are unclear.

The loudness target isn't specified, or the delivery spec conflicts with the mix.

Automatic subtitles or speech-to-text would publish or replace text the user hasn't checked.

FAILURE HANDLING

Audio missing or silent: check track mute, clip volume, and whether the source has an audio stream.

Crackle or clicks at cuts: add short fades, then check the source.

Sync drift: check the camera and recorder clocks, then resync the long take.

Effect not found: search the audio effects library once, then ask.

Meter shows clipping: reduce the source gain before adding effects.

RELATED SECTIONS

K2: timeline editing (for J and L cuts)

K4: effects, keyframes, and transitions

K6: titles and graphics (for subtitles)

K9: rendering and delivery (for the loudness spec at export)

K6: Titles and Graphics

 

Load when adding text, lower thirds, logos, shapes, or subtitles.

PURPOSE

Titles and graphics tell the viewer who, where, what, and when. They have to be readable, placed inside safe areas, timed to the edit, and consistent with the rest of the project. A good title disappears into the film. A bad one pulls the viewer out of it. This section covers the title tool, text styling, graphic overlays, lower thirds, subtitles, and how to check all of it against the delivery format.

VERIFY ON SCREEN

The titler's name and location, its toolbar and property panels, the font list, template library, shape tools, and subtitle features can differ by version. Confirm each one on screen before use. If a feature described here isn't available, say so and use the closest tool that exists.

TITLE CLIP BASICS

A title clip is a generated clip with text, shapes, or both. It sits on a video track like any other clip and can be trimmed, moved, keyframed, and given effects.

Create a title clip with the project's add-title command (verify its location on screen). It opens the titler, where you set the text, style, background, and position.

Title clips take the project's frame size and frame rate. Check that the project resolution matches the delivery format before designing the title, because a title designed at one size can shift when moved to another.

A title clip's background can be transparent, a solid color, or a picture. Transparent backgrounds let the layers below show through, which is the usual choice for lower thirds.

TITLER LAYOUT AND SAFE AREAS

Turn on the safe-area guides in the monitor overlay options (confirm on screen) before placing text.

Title-safe area sits inside the inner frame. Keep all text inside it. Text near the edge can be cut off on some televisions and projectors.

Action-safe area is the outer frame. Keep faces and key action inside it.

For social formats (vertical or square), check the safe area for that aspect ratio separately. A title built for 16:9 may sit off-frame in 9:16.

Align text using the titler's horizontal and vertical alignment tools. Center alignment is a good default for single titles. Left alignment suits lower thirds and captions.

TEXT STYLE

Font: choose a legible face for the purpose. Sans-serif fonts read well on screens. Serif fonts suit formal or period pieces. Avoid decorative fonts for body text or small captions.

Font size is set in points or as a percentage of frame height, depending on the titler. Check readability at the delivery size. Small text that reads fine on a laptop can be unreadable on a TV.

Line spacing (leading) and letter spacing (tracking): small adjustments improve readability. Tight tracking on large display text looks professional.

Weight and style: bold, italic, and underline are available. Use bold for emphasis, not for whole paragraphs.

Color: choose high contrast against the background. White or light text on dark, or dark text on light. If the title must match a grade, check its color on the vectorscope. Avoid pure saturated colors for body text.

Outline and shadow improve legibility on busy backgrounds. Keep the offset and blur small. Heavy outlines look dated.

Opacity: a semi-transparent background box behind text improves legibility on moving backgrounds.

BACKGROUNDS AND SHAPES

Rectangle and ellipse tools draw shapes for lower-third bars, boxes, and accents. Confirm their names and their fill, stroke, and gradient options on screen.

Gradient fills can add depth. Keep gradients subtle and check them for banding, especially on large dark areas.

Shapes and text in the same title clip share a layer order inside the titler. Check the order when text is hidden behind a shape.

Align shapes to the same margins as the text. Alignment off by a few pixels is visible to viewers.

LOWER THIRDS

A lower third names a person or a place, usually in the bottom-left or bottom-right area inside the title-safe zone.

Typical structure: a primary line (name) and a secondary line (role or place), with a bar or accent shape behind them.

Timing: enter quickly, hold long enough to read, then exit. Check the read time against the amount of text. Hold longer for more text.

Animate with simple moves: slide in, fade in, and slide out. Use keyframes on position or opacity. Keep the motion short and eased.

Consistency: the same lower-third style should appear across the whole project, with the same font, size, position, and color.

ANIMATING TEXT AND GRAPHICS

Titles and graphics animate with keyframes on position, scale, opacity, and rotation, using the transform controls in K3. Confirm the parameter names on screen.

Use the keyframe interpolation rules from K4: smooth for most motion, hold for switches.

Per-letter or typewriter animation may not be available in the titler. If it isn't, use a simple reveal (wipe or opacity) instead, and say so.

Motion templates or preset animations may be available in the template library. Check what each template does before applying it, and confirm it fits the project's frame size and style.

LOGOS AND IMAGE OVERLAYS

Import logos as PNG or another format with alpha, so the background is transparent. A JPEG logo shows a box.

Check the logo's resolution against the project. Scaling up a small logo softens it, so use a larger source where possible.

Place the logo inside the safe area, at a consistent size across the project.

Keep logos on their own track, so they can be muted, hidden, or moved without touching titles.

Logo usage rights: confirm the client or owner approves the logo's use and placement before rendering.

SUBTITLES AND CAPTIONS

Subtitles are text aligned to speech. Kdenlive has a subtitle workflow that can include speech-to-text where the installed version supports it. Verify the feature exists before relying on it.

Automatic subtitles mishear names, terms, and accents. Check every line against the audio, then correct timing and spelling by hand.

Subtitle timing: keep each subtitle on screen long enough to read, within the reading-speed limit. Avoid more than two lines, and keep line length within the delivery spec. Broadcast and streaming specs vary, so confirm them.

Position subtitles in the title-safe area, usually bottom center, and avoid covering on-screen text or faces.

Export subtitles as a separate file when the delivery needs it, such as SRT. Check which export formats the installed version supports.

Cut subtitles at natural speech breaks, not in the middle of a phrase.

TEMPLATES AND REUSE

Save a finished title style as a title template when it will be reused. Name templates by purpose, such as "Lower third bar white 2 line."

Keep a master set of titles and logos in a bin folder so the look stays consistent across a long project.

If a title is reused on another machine, check its fonts are installed there. A missing font can change the look or fail to render.

CHECKING GRAPHICS

Check each title at its first frame, last frame, and midpoint.

Watch readability on the brightest and darkest frames of the scene.

Check against the safe areas at the final render size.

Check fonts and logos in the rendered output, not only in the timeline.

Play the full sequence and check that titles don't overlap, flicker, or appear early or late.

PRACTICAL RULES

Titles should serve the viewer. Ask whether the viewer needs this information and whether they can read it in the time given.

Use one or two fonts across a project. More than that looks disorganized.

Use fewer animations. One consistent motion style reads as more professional than many different effects.

Keep titles off the lowest and highest parts of the frame when faces are present, to avoid collisions.

Avoid text on busy patterns without a backing box or shadow.

Match the title's color and temperature to the grade, not to a generic white.

STOP AND ASK WHEN

A name, spelling, or fact in a title or subtitle hasn't been confirmed.

A logo's use or placement isn't approved.

A title would cover on-screen text, faces, or key action.

Subtitles were generated automatically and haven't been checked.

The title's language, font, or style doesn't match the project's brief.

A delivery spec for subtitles, safe areas, or text size isn't known.

FAILURE HANDLING

Title not visible: check track order, track visibility, the title's opacity, and whether the background is transparent when it should be.

Font missing or substituted: check the font list, install the font if needed, and reopen the title to confirm.

Text clipped at the edge: check safe-area placement, then reposition in the titler.

Animation not playing: check keyframes on the title clip and their interpolation.

Subtitle timing wrong: check speech alignment and subtitle duration, then retime by hand.

Template won't apply: check the template's frame size and the installed version's support, then report what you see.

RELATED SECTIONS

K3: tracks, compositing, and transforms

K4: effects, keyframes, and transitions

K5: audio (speech for subtitles)

K7: color tools (matching title colors to the grade)

K9: rendering and delivery (fonts, subtitle export, final check)

K7: Color Tools in Kdenlive

 

Load when correcting or grading color in Kdenlive.

PURPOSE

Kdenlive can grade footage, but it uses a per-clip effect stack rather than a node graph like DaVinci Resolve. This section maps the grading guide onto Kdenlive's tools. Correction comes first, then skin, then regions, then shot matching, then the creative look. A LUT is never the grade on its own. It is a starting point or a technical conversion, and the result must be adjusted by hand.

FOLLOW THE GRADING GUIDE

The grading guide is the authority for order, targets, and pitfalls. This section covers how to do each step in Kdenlive. Where the guide says to check the vectorscope, do that in Kdenlive's scope panel. Where it says to stop and ask, do that too.

VERIFY ON SCREEN

Effect names, parameter names, scope panel options, LUT loading steps, and curve editor behavior can change between versions. Version notes are in K1. Check Help > About for the installed version, and confirm each name on screen before use. Report any difference.

COLOR PIPELINE IN KDENLIVE

Project color settings: set the project profile (resolution, frame rate, and color space where exposed) to match the delivery. Confirm on screen.

Clip effect stack: color effects are added per clip, in order. Order matters. Corrections go above creative effects.

Track and master effects: use only for shared looks, after clip-level correction is set. Check that they don't fight the clip grade.

Preview: check the project monitor's playback quality. Low quality can mislead color decisions. Set it to full quality for grading.

SCOPES

Open the scopes panel (verify location on screen). Use the waveform, RGB parade, vectorscope, and histogram as described in the grading guide.

Read scopes on a representative frame before adjusting. Read them again after each change.

Scopes reflect the monitor output. If the monitor is in a different mode, the readings may not match the delivered image. Confirm the monitor mode.

Keep scope panels visible while grading so the readings sit alongside the monitor.

TECHNICAL CONVERSION (INPUT)

Log footage: apply the correct technical LUT or input conversion for the camera before any grading. Load the manufacturer's .cube file through a LUT effect, and set the LUT's intensity to full. Confirm the LUT matches the camera and log format, since a wrong LUT is a common cause of a muddy start.

Rec.709 footage: no input conversion needed. Go straight to primary correction.

Raw footage: raw processing happens outside the grade. Set white balance and exposure in the raw settings first, if the installed version supports it.

Verify after conversion: the waveform should show detail across the range without clipping at either end. If it doesn't, stop and check the LUT.

PRIMARY CORRECTION TOOLS

Lift, gamma, and gain (or equivalent three-way controls) map to the black point, midtones, and white point in the grading guide. Confirm the exact control names on screen. Set each value by typing where possible.

Lift: set the black point just above 0 IRE, with no crush.

Gain: set the white point near 90 to 100 IRE, with no clipping on skin or fabric.

Gamma: set midtones until faces look natural.

Color wheels shift color in shadows, midtones, and highlights. Use them to neutralize white balance against a neutral surface on the RGB parade, or to move toward the intended tone. Make small moves and check the vectorscope.

White balance (temperature and tint): if the installed version offers a white balance effect, use it as the first step for color casts. Otherwise use the color wheels.

Levels set input and output black and white points. Useful for precise black and white placement. Keep output range within legal levels for broadcast delivery.

Contrast and brightness are broad controls. Use them after the three-way controls are set, not before.

Saturation: global saturation is blunt. Set it after white balance and contrast, and check the vectorscope.

CURVES

RGB curves adjust luminance and each channel. Use them for fine contrast and for shaping highlights and shadows. Keep the S-curve gentle.

Hue versus saturation curves adjust saturation for one hue range. Use them to tame a single loud color, such as a red garment, without touching skin.

Hue versus luminance curves adjust brightness for one hue range.

Saturation versus luminance curves reduce saturation in very bright or very dark areas if they look neon.

Verify on screen which curves the installed version provides and how to select a point. Type values where possible.

SKIN ANCHOR

Skin lives on the vectorscope skin tone line. Read skin on the vectorscope and RGB parade on a face-rich frame.

Correct skin in the primary first when the cause is global, such as a green or magenta cast from the light.

Move to a face mask (K3, and K8 for mask tools) only for regional problems, such as one face lit differently.

REGIONAL CORRECTION (SECONDARIES)

Use the color-range or hue-based selection tools available in the installed version, then combine them with masks from K3. Follow the region order in the grading guide: skin first, then eyes, hair, lips, clothing, props, background, foreground, highlights, shadows.

Keep each mask feathered. Check the matte on a solid background if the version offers a matte view. Track masks through motion (K3).

Kdenlive's mask and key tools are simpler than Resolve's. If a region can't be isolated cleanly, say so and skip it rather than forcing a bad mask.

LUTS (CREATIVE)

A creative LUT is applied after the correction is set, not in place of it.

Apply the LUT, then reduce its intensity if it overshoots. Check skin on the vectorscope and waveform after the LUT, since LUTs often shift skin.

Use a LUT built for the camera and format. A LUT for another camera or light may look wrong.

Don't stack multiple LUTs. Use one creative LUT and correct around it.

SHOT MATCHING IN KDENLIVE

Pick a reference shot in the scene. Confirm it is correct before matching.

Match in the grading guide's order: exposure and contrast (lift, gain, gamma), then white balance, then skin, then secondary elements.

Copy and paste effect stacks between shots as a starting point, then adjust each shot's values by hand. Pasted values rarely match exactly.

Play every cut through in real time. Matching is judged in motion, not on still frames.

CREATIVE LOOK

Only after the steps above are done. Keep the look subtle.

Propose one look in one sentence and wait for approval before applying it.

Grain and vignettes: small amounts. Check at delivery size.

Halation or bloom: only if the look calls for it and the render holds up.

CHECKS BEFORE DELIVERY

Legal levels: confirm the waveform stays within 0 to 100 IRE for broadcast.

Continuity: play the full sequence and watch skin and color at every cut.

Review on the output view and, where possible, on a second display.

Render a short test clip first, then check the exported file, not only the timeline. Compression can shift the look.

PRACTICAL RULES

Correct before you style. Never hide a bad correction under a creative look.

Work with the scopes, not only the eye.

Label each effect so the stack can be reviewed.

Make one change at a time, then check the scopes and playback.

Small moves beat big ones. If a change is obvious, it is probably too strong.

STOP AND ASK WHEN

The input conversion produces a badly wrong image and no correct LUT is available.

A creative look would clip skin or crush fabric.

A mask fails on several frames or leaves visible halos.

The reference contradicts the footage, such as a daylight reference for a tungsten scene with no plan for mixed light.

A creative choice changes the story's mood beyond the agreed look.

A render or export is requested.

FAILURE HANDLING

Control or effect not found: search the effect library once, then ask.

Image looks wrong after the LUT: check that the LUT matches the camera and format, and reduce its intensity.

Scopes don't match the monitor: check the scope mode and monitor output.

Skin shifts at a cut: check the shot-matching order, then compare the shots on the vectorscope.

Playback stutters while grading: switch preview quality or use proxies (K8), then report what you see.

RELATED SECTIONS

Grading guide: the authority for order, targets, and pitfalls

K3: tracks, compositing, and masks

K4: effects and keyframes

K8: proxies and playback performance

K9: rendering and delivery

K8: Media Management and Proxies

 

Load when importing, organizing, relinking, or improving playback.

PURPOSE

Media management decides whether a project survives its own growth. Clean bins, correct links, consistent frame rates, and smooth playback make editing faster and safer. Most lost work in editing comes from moved files, offline media, and unmanaged proxies, so this section sets rules for keeping media findable, linked, and backed up.

VERIFY ON SCREEN

The import dialog, bin layout, proxy settings, cache location, relink and archive commands, and transcoding options can differ by version. Version notes are in K1. Confirm every name and location on screen before use.

HOW KDENLIVE HOLDS MEDIA

The project file (.kdenlive) stores references to media files. It does not contain the media. If files move or are renamed, the project shows them as offline until relinked.

The Project Bin holds clips, sequences, folders, and their metadata. Bin items point to files on disk. Deleting a bin clip can remove it from the project, but the file on disk stays unless the user explicitly deletes it.

Proxies, thumbnails, and render caches are separate files that Kdenlive creates. They can be regenerated, and they can take large amounts of space.

The project folder and the cache folder are different locations. Confirm where each one is in the project settings on screen.

IMPORT

Import media through the project's add-clip or import command, or by dragging files from the file browser into the bin. Confirm the import options on screen.

Import to a folder structure that mirrors the production, for example Footage/Camera A/Day 1, Audio/Dialogue, Music, Graphics, Exports. Do not import everything into the bin root.

Check each imported clip's properties: duration, frame rate, resolution, audio sample rate, codec, and whether it has audio and video streams.

Mismatched frame rates or resolutions cause problems on the timeline. Note them at import, not during the edit.

Some folder imports create many clips at once. Check the count and remove unwanted files before the edit starts.

PROJECT SETTINGS THAT MATTER

Project profile: resolution, frame rate, and aspect ratio. Set them to match the delivery format before placing clips. Changing the profile after clips are placed can change how the timeline plays back and can alter placed clips. Ask before changing it on a live project.

Audio sample rate: match the footage where possible, usually 48 kHz.

Folder locations: set the project folder and cache folder to a drive with enough space and speed. Confirm the path on screen.

BIN ORGANIZATION

Use bin folders by type and by scene, not by date alone. A common structure: Footage, Audio, Music, Graphics, Titles, Sequences, Exports.

Name clips consistently, such as SC01_TK03_CamA. Use the same convention for the whole project.

Use clip markers and comments in the bin to note takes, selects, and problems. Add ratings or labels if the version supports them (verify on screen).

Keep sequences in their own folder. Keep master sequences separate from working or versioned sequences.

Keep an unused or reference folder for material not used in the cut. Don't delete material from the project until the cut is locked.

RELINKING

Offline clips show a warning or placeholder when their file is missing. Find the cause before relinking: the drive may be disconnected, or the file may have been renamed or moved.

Relink by choosing the new location for the clip or for the folder. Confirm the relink on screen by checking the clip's status and the timeline preview.

Relink a folder when many clips moved together. Check a sample of clips after relinking, especially audio and any clip with a different extension.

Never relink to a file with different content or a different frame count, since that breaks sync and effects. Check duration and frame rate first.

If a file is truly missing, stop and ask the user. Don't replace it with a similar-looking file.

PROXIES

A proxy is a smaller, lighter copy of the source used for editing. The original is still used for the final render. Proxies make playback smoother on slower machines and with heavy codecs.

Create proxies from the bin or the project settings, using the proxy option available in the installed version. Choose the resolution and codec from the options shown on screen. Common targets are a smaller frame size, such as half resolution, in an edit-friendly codec.

Enable proxy use only after the proxies are generated and checked. Confirm on screen which clips use proxies and which use the original.

A proxy and its original must match in duration, frame rate, and frame count. A proxy with a different length causes drift.

Before rendering, switch to original media, and check that the render uses the originals, not proxies. Some versions have a setting for this. Verify on screen.

Proxies take disk space. Delete them only when the project is finished and the user approves, since regenerating them takes time.

PLAYBACK PERFORMANCE

Check the project monitor's playback quality setting. Lower quality speeds up playback but can mislead color and detail decisions. Use full quality for grading and finishing.

Timeline preview rendering can speed up playback of heavy effects. Clear previews when the timeline changes a lot. Verify the preview setting on screen.

Clear caches when they grow large or when playback looks wrong. Ask before clearing caches on a project in progress, since rebuilding takes time.

Use hardware decoding if the machine supports it and the option appears on screen. Check for stability after enabling it.

TRANSCODING

Transcoding converts media to a different codec or format. Use it only when the codec causes playback or compatibility problems.

Keep the original files. Store transcodes separately, and check each transcode against the original for quality, frame rate, and audio sync.

Never transcode a delivery master without a check.

BACKUP AND ARCHIVING

Keep the project file and media on at least two separate drives or locations.

Archive or collect the project when handing it off or closing it. Use the project archive or consolidate option if the installed version has one. Confirm on screen what it copies (media, proxies, cache).

Save versions before major changes: File > Save As with a version suffix, such as project_v03.kdenlive. Keep older versions until the project is delivered.

Keep a written list of files and their locations for each project. Note external assets such as fonts, LUTs, and music licences.

FONTS, LUTS, AND EXTERNAL ASSETS

Fonts used in titles must be installed on any machine that opens the project. Note missing fonts and install them before opening the project elsewhere.

LUT files must travel with the project. Store them in a project folder.

Music and stock assets need their licence records stored with the project.

PRACTICAL RULES

Set up the bin and folder structure before the first import. Changing it later takes longer and causes more mistakes.

Keep the source, the proxy, and the project file in a clear, predictable layout.

Check every new drive for speed and space before a project starts on it.

Test relinking and archiving once on a copy before a deadline.

Verify the originals are used in the final render.

STOP AND ASK WHEN

Media is offline and its location is unknown.

A relink candidate doesn't match the original's duration, frame rate, or content.

A cache, proxy, or transcode would be deleted or regenerated on a live project.

The project profile or sample rate would change on a live timeline.

An archive or consolidate action would copy or move files outside the project folder, or would copy licensed material to a new location.

Any original file would be deleted, moved, or overwritten.

FAILURE HANDLING

Clip offline after a move: check whether the drive is connected, then relink the folder once. Report if the relink fails.

Playback stutters: check proxy use, playback quality, and cache, then report what you see before changing settings.

Proxy out of sync: regenerate the proxy for that clip, then check its duration against the original.

Render uses proxies: stop, switch to original media, and render a test clip to confirm.

Import shows wrong frame rate or missing audio: check the file's properties and codec, then report before re-importing.

RELATED SECTIONS

K2: timeline editing and trimming

K5: audio, for sample rate and sync

K7: color tools, for full-quality preview during grading

K9: rendering and delivery, for output from originals

K9: Rendering and Delivery

 

Load when exporting, rendering a zone, or preparing a final file.

PURPOSE

Rendering turns the timeline into a file that someone else will watch, hear, or upload. A render is permanent for that file: once it's out, mistakes are in the world. This section sets the checks that come before every render, how to choose settings for each destination, and how to verify the output afterwards.

VERIFY ON SCREEN

The render window, preset names, codec options, encoder availability, zone rendering, and audio export settings can differ by version and by the FFmpeg and MLT builds installed. Version notes are in K1. Confirm each setting on screen before use. If a preset or encoder is missing, report it and choose the closest available option.

BEFORE ANY RENDER: PRE-FLIGHT CHECK

Do all of these before opening the render window. A render that starts too early wastes time and can produce a file that has to be redone.

Confirm the sequence is the correct one, and that it is the approved version (check the sequence name and version suffix).

Check the project profile (resolution, frame rate, aspect ratio) against the delivery spec. Do not change the profile on a finished timeline without asking.

Use the original media, not proxies (K8). Confirm on screen.

Play the full sequence at full playback quality and listen to the whole mix.

Check the timeline for unintended gaps, overlaps, offline clips, and disabled tracks that should be on.

Check track targeting, mute, and hide states. A hidden track can drop out of the render, and a muted audio track can drop out of the mix.

Check titles, subtitles, and graphics against the safe areas (K6).

Check the color (K7) and the audio levels and loudness (K5) on the master.

Clear the render queue and any leftover zone or in-and-out marks that shouldn't apply to this export.

Check the output folder, file name, and free disk space. Don't render over an existing file without asking.

RENDER TARGETS

Full sequence renders everything between the first and last frame of the sequence.

In and out (work area or zone) renders only the marked region. Use it to test a fix or to export a single segment. Confirm the marks before rendering. Stale marks are a common cause of incomplete exports.

Selected clips or tracks: some versions can render a selection. Confirm the option on screen before using it.

CHOOSING A PRESET

Use a preset when it matches the destination. Check each preset's frame size, frame rate, codec, container, and audio on screen before choosing it.

Use a custom render only when the destination requires settings no preset offers, and write the chosen settings down.

Common destinations and their general needs. Confirm the exact spec with the client or platform.

Web or streaming: H.264 or H.265 in MP4, AAC audio, with a bitrate that matches the resolution and frame rate. Loudness near the platform target.

Broadcast: follow the broadcaster's spec. This often means a specific codec, bitrate, frame rate, frame size, and audio levels. Ask for the spec if it isn't provided.

Archive or master: a high-quality or lossless intermediate format, so later versions can be made without losing quality. Confirm the codec and container with the user.

Social vertical or square: a frame size for that aspect ratio, with safe areas checked for that shape.

Still frame or image sequence: for thumbnails or handoff to other tools. Check naming and the frame range.

VIDEO SETTINGS

Frame size must match the delivery format. Do not upscale unless the destination requires it and the result is checked.

Frame rate must match the source or the delivery spec. Changing frame rate at render can cause judder or duplicate frames. Match the sequence where possible.

Codec: H.264 is widely compatible. H.265 is smaller at the same quality but may not play everywhere. ProRes or other intermediate codecs suit editing handoff. Confirm the codec on screen and against the spec.

Quality and bitrate: use the preset's quality setting, or a bitrate chosen for the frame size and frame rate. Higher bitrate reduces compression artifacts but increases file size. Check banding and blocking on dark gradients after rendering.

Chroma subsampling: 4:2:0 is standard for delivery. Higher subsampling is for intermediates and grading handoffs. Confirm it matches the spec.

Bit depth: 8-bit for standard delivery, higher for HDR or master files. Check that the codec supports the chosen bit depth.

Color space: match the sequence's output color space, for example Rec.709 for HD delivery. Do not mix a Rec.709 export with a wide-gamut sequence without a conversion. Confirm the color settings on screen.

Field order and scanning: progressive for most delivery. Confirm if a broadcaster requires interlaced.

Pixel aspect ratio: square pixels for most delivery. Check whether the project uses anamorphic footage.

AUDIO SETTINGS

Audio codec: AAC is common for MP4 delivery. PCM is used for masters and handoffs.

Sample rate: 48 kHz for video. Match the project.

Channels: stereo for most delivery. Mono or multichannel only if the spec calls for it.

Bitrate: match the platform or spec. Higher bitrate helps music and effects.

Loudness: check the master against the target before rendering (K5). A limiter on the master should protect the peak ceiling.

Export audio separately when a client or distributor needs stems or a separate mix. Confirm the option on screen.

FILE AND NAMING

Name the output with a clear pattern, such as ProjectName_v03_1080p25_H264.mp4. Include the version, resolution, frame rate, and codec where that helps.

Keep the output in a dedicated Exports folder, not next to the project file.

Keep subtitle and caption files with the video file, using the same base name.

Don't overwrite an existing export without asking. Keep the previous version until the new one is approved.

RENDER QUEUE

Add the render job to the queue, check its settings, then start the queue. Confirm the job's details on screen before starting.

Run one job at a time when the machine is limited. Running several jobs can slow every one of them.

Watch the render for errors in the log. Note any warning about missing media, unsupported codecs, or failed effects.

Don't edit the timeline while a render is running unless the version supports it safely. Confirm this on screen before changing anything.

VERIFY AFTER RENDERING

Open the exported file in a separate player, not only the timeline.

Check the first frame, the last frame, and several frames across each cut.

Check the audio: listen to the whole file, check for clipping, and check sync at the start, middle, and end.

Check the frame size, frame rate, codec, bit depth, and duration against the spec, using the file's properties.

Check the color on a reference monitor if available. Compare with the timeline and the scopes.

Check text, subtitles, and safe areas in the exported file.

Check for banding, blocking, and crushed shadows in dark areas.

If the file will be uploaded, play it at the platform's likely playback settings, such as on a phone or a TV.

Keep the render log and the settings used with the project for later.

COMMON RENDER PROBLEMS

Black frames or missing content: check that tracks are enabled, clips are online, and the render range is correct.

Audio missing or out of sync: check audio tracks, mute states, sample rate, and whether audio export is enabled.

Stutter or dropped frames in the file: check render settings, frame rate match, and whether proxies were used.

Banding in gradients: raise bitrate or bit depth, or add grain or dither upstream (K7).

File too large or too small: adjust bitrate, not frame size, unless the spec requires a different frame size.

Colors look wrong in the export: check the output color space and the player's color handling.

PRACTICAL RULES

Render a short test clip with the final settings before the full export.

Keep the master file as the source for all other deliveries, rather than re-encoding a delivery file.

Never deliver a file you haven't watched from start to end.

Keep a record of the settings used for every delivered file.

STOP AND ASK WHEN

The delivery spec is not known, or it conflicts with the sequence settings.

The render range, sequence, or version is unclear.

Output would overwrite an existing file.

A preset would change frame rate, frame size, or color space from the sequence.

A broadcast or platform requirement is not confirmed.

The file is being sent to a client or platform, not kept internally.

A render error or missing media appears in the log.

FAILURE HANDLING

Render fails: read the error in the log, check missing media, codec, and disk space, then report before retrying.

Exported file won't play: check the codec and container against the player, then re-render with a more compatible preset after asking.

Export looks different from the timeline: check color settings, playback quality, and whether proxies were used, then compare frame by frame.

Render too slow: check whether other jobs are running, and whether effects need a preview render first.

Preset not found: search the render presets once, then ask.

RELATED SECTIONS

K5: audio and loudness

K6: titles, subtitles, and safe areas

K7: color tools and the grading guide

K8: proxies and original media

K10: shortcuts and workspace

K10: Keyboard Shortcuts and Workspace

 

Load when a task needs a key, a layout, or a workspace setup.

PURPOSE

Shortcuts and layout decide how fast an editor works and how reliably they stay in control of the edit. This section gives the AI a safe way to use shortcuts, set up a workspace for a task, and avoid accidental changes. It does not replace the on-screen check.

VERIFY ON SCREEN

Default shortcut keys can differ by version, by operating system, and by any custom keymap the user has set. The shortcuts named in other sections are common defaults and must be confirmed before use. Version notes are in K1. Open Settings > Configure Shortcuts to see the active keymap, and use what is shown there. Where a shortcut isn't listed, use the menu.

SHORTCUT RULES

Never assume a shortcut. Confirm it in the menu, the tooltip, or the shortcut editor before pressing it.

Prefer menu commands when the action is destructive or unclear. A menu item shows its shortcut next to the command, which doubles as a check.

Check the active tool and track target before pressing an editing key. Many keys act on the selected clip, the targeted track, or the playhead, and the same key does different things in different panels.

Check focus. A key pressed while a text field is active types text instead of acting on the timeline. Click an empty part of the panel or press Escape before using shortcuts, then confirm with a screenshot.

Don't use a timeline shortcut while the monitor or bin is focused, unless the shortcut is confirmed for that panel.

Keep track of modifiers: Shift, Ctrl (Cmd on macOS), and Alt each change the result. Confirm the modifier on screen.

Undo (Ctrl+Z, or Cmd+Z on macOS) is the first recovery step. Confirm the undo in a screenshot, and don't chain several undos without checking each.

COMMON ACTION GROUPS (verify each name and key on screen)

Playback: play and pause, step one frame forward and back, jump to start and end, play in reverse, and the J K L shuttle controls. J reverses, K pauses, L plays forward. Repeated J or L speeds the shuttle.

Marks and points: set in and out on the clip or the timeline, clear them, and go to a mark. Stale marks cause wrong placements, so check them before any insert or overwrite.

Editing: cut at the playhead, insert, overwrite, lift, extract, and delete. Lift removes material and leaves a gap. Extract removes material and closes the gap. Confirm the difference on screen before using either.

Tools: switch between selection, razor, and the trim modes covered in K2. Confirm the active tool on the toolbar after switching.

Timeline navigation: zoom in and out, fit the timeline to the window, and move the playhead to the next or previous clip or marker.

Panels: show or hide the bin, monitors, effect stack, scopes, audio mixer, and titler. Confirm the panel names in the Window or View menu.

Save and undo: save, save as, undo, and redo.

Render: open the render window and queue a job. Never start a render from a shortcut without checking the settings first (K9).

WORKSPACE

Kdenlive lets the editor arrange panels and save the arrangement as a workspace layout. Use the workspace menu to switch or save a layout. Confirm the names on screen.

Use one workspace for editing, another for color, and another for audio. Switch when the task changes.

A good editing layout keeps the project monitor large, the timeline visible across most of the bottom, and the bin and effect stack reachable.

A color layout shows the scopes next to the monitor, with the effect stack and color panel visible. Keep the scopes visible while grading (K7).

An audio layout shows the audio mixer and meters with the timeline.

Reset a workspace from the workspace menu if panels are lost or cramped. Confirm the reset on screen, since it can remove custom panel positions.

CUSTOM SHORTCUTS

A custom keymap can change any default. Check the active keymap before assuming a default.

Create new shortcuts only for actions the editor uses often, and record them so the setup is repeatable. Confirm they don't conflict with other shortcuts.

Don't remap keys used by the operating system or by other apps the editor relies on. Check for conflicts in the shortcut editor.

Export and import shortcut settings when setting up a second machine. Confirm the option on screen.

FOCUS AND SAFETY

Before a sequence of keys, confirm the focus with a screenshot.

Stop after any unexpected result. Take a fresh screenshot before the next key.

Never press a key repeatedly to fix a problem. Each press may compound the error. Undo once, check, then continue.

Save the project before large operations, and save a version before major changes (K8).

ACCESSIBILITY AND ERGONOMICS

Adjust the interface scale in preferences if text is too small to read reliably in screenshots. Confirm the change on screen.

Keep the most-used actions reachable from the keyboard, with the pointer on the timeline or monitor.

Use a larger timeline track height when clips are hard to target.

PRACTICAL RULES

Learn the three things that matter most first: play and stop, cut at the playhead, and undo. Everything else is built on them.

Don't memorize shortcuts you don't use. Use the menu, and add shortcuts later for actions you repeat.

Name workspaces by task so the right layout is easy to find.

Keep one shortcut setup per project team, so every editor works the same way.

STOP AND ASK WHEN

A shortcut would delete, overwrite, or render something, and the target is not clearly confirmed.

The active keymap differs from the defaults named in this reference, and the difference changes the action.

A custom shortcut would conflict with a system or app shortcut the user relies on.

A workspace reset would remove a layout the user has set up for a live task.

FAILURE HANDLING

Shortcut does nothing: check focus, then the active tool and track target, then look up the shortcut in Configure Shortcuts.

Shortcut did the wrong thing: undo once, take a screenshot, and report what happened before trying again.

Panel missing: open the Window or View menu, check the panel is enabled, and reset the workspace only if needed.

Key sticks or repeats unexpectedly: release the key, click a neutral area, and check the state before continuing.

RELATED SECTIONS

K2: timeline editing and trimming (edit keys and tool modes)

K7: color tools (grading workspace and scopes)

K9: rendering and delivery (render shortcuts and checks)          

3
