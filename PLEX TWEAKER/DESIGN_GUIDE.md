# Meow Ware Design Guide

## Product character

Meow Ware should feel calm, precise, and native to a desktop utility. Use a restrained black interface with white outlines and accents. Avoid decorative gradients, oversized cards, excessive glow, emoji, and visual effects that do not communicate state. All interface icons must be SVG components from the shared icon library.

## Motion standard

Every visible state change should feel smooth and intentional. Components must not abruptly appear, disappear, resize, or jump unless immediate feedback is required for safety.

- Use `160–220ms` for dropdowns, tooltips, buttons, toggles, and small controls.
- Use `220–280ms` for modals, drawers, panels, and view transitions.
- Use `cubic-bezier(.16, 1, .3, 1)` for entrances and expanding motion.
- Use `ease-in` or `cubic-bezier(.4, 0, 1, 1)` for exits.
- Animate only `opacity` and `transform` whenever possible. Avoid animating layout properties that cause reflow.
- Opening elements should fade in while moving no more than `6–10px` or scaling from approximately `.97`.
- Closing elements must remain mounted until their exit animation finishes.
- Hover feedback should be subtle and finish within `160–180ms`.
- Chevron SVGs rotate smoothly when their dropdown opens.
- Selected menu items use the shared SVG check icon. Never use text check marks or emoji.
- Preserve spatial continuity: dropdowns originate from their trigger, drawers from their attached edge, and modals from the center.
- Do not stack unrelated animations. One clear transition is preferable to multiple competing effects.

## Component behavior

### Modals

Modals use a blurred, fading backdrop and a small fade/scale/vertical transition. The close animation must complete before unmounting. Browser-native `alert()` and `confirm()` dialogs are not permitted; use the shared `Modal` component.

### Dropdowns and menus

Dropdowns remain mounted while closing so both directions animate. They use the same easing and duration across custom selects, account menus, license menus, process menus, and compact navigation. Menus must never be clipped by a scrolling parent.

### Navigation and panels

Navigation selection changes should animate color, outline, and label width without shifting surrounding controls. Panels and terminal drawers should expand within the layout rather than floating over unrelated content.

### Window controls

Minimize, maximize, restore, and exit may use a restrained opacity/scale transition before the native window operation. Window motion must remain quick and must not delay the requested action noticeably.

### Buttons and inputs

Buttons transition color, border, and background consistently. Inputs and custom selects use smooth focus and validation states. Avoid `transition: all`; list the properties that actually change.

## Accessibility

All motion must respect `prefers-reduced-motion: reduce`. In reduced-motion mode, remove nonessential animations and transitions while preserving state changes, focus visibility, and usability.

## Themes

Themes must be implemented through shared CSS tokens so every view updates consistently. Preset themes require a compact palette preview and a clear selected state using the SVG check icon. Custom colors use the shared color-picker component, preview immediately, and are not persisted until the user explicitly saves them. Custom CSS is local, length-limited, and loaded after the core stylesheet so advanced users can override tokens without modifying application files. Switching themes or source categories should use a short fade-and-translate transition to preserve context.
