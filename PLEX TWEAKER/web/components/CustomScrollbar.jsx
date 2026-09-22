import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';

/**
 * CustomScrollbar — reusable overlay scrollbar that matches the Meow Ware design language.
 *
 * Why this exists: every other control in the app is custom-styled, but scrolling still fell
 * back to the thin native bar. This paints our own thumb over the content so it looks identical
 * in every scroll area (`<CustomScrollbar className="the-old-scroller">…</CustomScrollbar>`).
 *
 * Behaviour:
 *  - Hides the native scrollbar and overlays a themed thumb — no layout shift, no reserved gutter.
 *  - Tracks content changes (rows added / removed / filtered) via ResizeObserver + MutationObserver,
 *    so the thumb size and position stay correct as items come and go.
 *  - Auto-hides when idle and fades back the instant you scroll, hover, or drag. The fade-out is the
 *    "smooth while closing" motion from DESIGN_GUIDE.md.
 *  - Thumb dragging + click-to-page on the rail, and honours prefers-reduced-motion (no fade,
 *    instant jumps) while keeping native wheel / keyboard / touch scrolling fully intact.
 */
const MIN_THUMB = 28;

export default function CustomScrollbar({
  children,
  className = '',
  viewportClassName = '',
  contentClassName = '',
  autoHide = true,
  hideDelay = 1100,
  onScroll,
  ...rest
}) {
  const viewportRef = useRef(null);
  const contentRef = useRef(null);
  const railRef = useRef(null);
  const hideTimer = useRef(0);
  const dragState = useRef(null);

  const [thumb, setThumb] = useState({ size: 0, offset: 0, overflow: false });
  const [visible, setVisible] = useState(!autoHide);
  const [dragging, setDragging] = useState(false);

  const reduceMotion = typeof window !== 'undefined'
    && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

  /* Recompute thumb geometry from the live scroll metrics. */
  const measure = useCallback(() => {
    const vp = viewportRef.current;
    if (!vp) return;
    const { clientHeight, scrollHeight, scrollTop } = vp;
    if (scrollHeight - clientHeight <= 1) {
      setThumb((prev) => (prev.overflow ? { size: 0, offset: 0, overflow: false } : prev));
      return;
    }
    const size = Math.max(MIN_THUMB, Math.round((clientHeight / scrollHeight) * clientHeight));
    const maxScroll = scrollHeight - clientHeight;
    const maxOffset = clientHeight - size;
    const offset = maxScroll > 0 ? Math.round((scrollTop / maxScroll) * maxOffset) : 0;
    setThumb({ size, offset, overflow: true });
  }, []);

  const reveal = useCallback(() => {
    setVisible(true);
    if (!autoHide) return;
    window.clearTimeout(hideTimer.current);
    hideTimer.current = window.setTimeout(() => {
      if (!dragState.current) setVisible(false);
    }, hideDelay);
  }, [autoHide, hideDelay]);

  const handleScroll = useCallback((event) => {
    measure();
    reveal();
    onScroll?.(event);
  }, [measure, reveal, onScroll]);

  /* Keep the thumb honest while content is added, removed, or resized. */
  useLayoutEffect(() => {
    measure();
    const vp = viewportRef.current;
    const content = contentRef.current;
    if (!vp) return undefined;

    const ro = new ResizeObserver(() => measure());
    ro.observe(vp);
    if (content) ro.observe(content);

    let mo;
    if (content && typeof MutationObserver !== 'undefined') {
      mo = new MutationObserver(() => measure());
      mo.observe(content, { childList: true, subtree: true, characterData: true });
    }
    return () => { ro.disconnect(); mo?.disconnect(); };
  }, [measure]);

  /* Flash the bar once on mount so overflow is discoverable, then let it settle. */
  useEffect(() => { reveal(); return () => window.clearTimeout(hideTimer.current); }, [reveal]);

  const onThumbPointerDown = useCallback((event) => {
    const vp = viewportRef.current;
    if (!vp) return;
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.setPointerCapture?.(event.pointerId);
    dragState.current = {
      startY: event.clientY,
      startScroll: vp.scrollTop,
      moveRange: vp.clientHeight - thumb.size,
      scrollRange: vp.scrollHeight - vp.clientHeight,
    };
    setDragging(true);
    setVisible(true);
    window.clearTimeout(hideTimer.current);
  }, [thumb.size]);

  const onThumbPointerMove = useCallback((event) => {
    const st = dragState.current;
    const vp = viewportRef.current;
    if (!st || !vp || st.moveRange <= 0) return;
    const delta = event.clientY - st.startY;
    vp.scrollTop = st.startScroll + (delta / st.moveRange) * st.scrollRange;
  }, []);

  const endDrag = useCallback((event) => {
    if (!dragState.current) return;
    dragState.current = null;
    setDragging(false);
    event.currentTarget.releasePointerCapture?.(event.pointerId);
    reveal();
  }, [reveal]);

  /* Click on empty rail space pages toward the pointer. */
  const onRailPointerDown = useCallback((event) => {
    if (event.target !== railRef.current) return;
    const vp = viewportRef.current;
    if (!vp) return;
    const rect = railRef.current.getBoundingClientRect();
    const ratio = (event.clientY - rect.top) / rect.height;
    vp.scrollTo({
      top: ratio * (vp.scrollHeight - vp.clientHeight),
      behavior: reduceMotion ? 'auto' : 'smooth',
    });
    reveal();
  }, [reduceMotion, reveal]);

  const onPointerLeave = useCallback(() => {
    if (!autoHide || dragState.current) return;
    window.clearTimeout(hideTimer.current);
    hideTimer.current = window.setTimeout(() => setVisible(false), 240);
  }, [autoHide]);

  const rootClass = [
    'custom-scrollbar',
    thumb.overflow && 'cs-has-overflow',
    visible && thumb.overflow && 'cs-visible',
    dragging && 'cs-dragging',
    className,
  ].filter(Boolean).join(' ');

  return (
    <div className={rootClass} onPointerEnter={reveal} onPointerLeave={onPointerLeave} {...rest}>
      <div className={`cs-viewport ${viewportClassName}`.trim()} ref={viewportRef} onScroll={handleScroll}>
        <div className={`cs-content ${contentClassName}`.trim()} ref={contentRef}>{children}</div>
      </div>
      <div className="cs-rail cs-rail-v" ref={railRef} onPointerDown={onRailPointerDown} aria-hidden="true">
        <div
          className="cs-thumb"
          style={{ height: `${thumb.size}px`, transform: `translateY(${thumb.offset}px)` }}
          onPointerDown={onThumbPointerDown}
          onPointerMove={onThumbPointerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
        />
      </div>
    </div>
  );
}
