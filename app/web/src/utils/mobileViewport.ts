/** Identify on-screen keyboard occlusion without mistaking user pinch zoom for a keyboard.
 * VisualViewport.height decreases with BOTH keyboard and pinch zoom. Convert
 * visual viewport height into layout-viewport pixels before measuring loss.
 * Panning changes offsetTop without changing the occluded height.
 */
export function isMobileKeyboardVisible(
  layoutHeight: number,
  viewport: Pick<VisualViewport, 'height' | 'offsetTop' | 'scale'> | null,
): boolean {
  if (!viewport) return false
  const scale = Number.isFinite(viewport.scale) && viewport.scale > 0 ? viewport.scale : 1
  return layoutHeight - scale * viewport.height > 150
}
