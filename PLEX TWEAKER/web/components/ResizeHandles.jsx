import { useCallback } from 'react';
import { callDesktop } from '../lib/desktopApi';

const MIN_WIDTH = 800;
const MIN_HEIGHT = 600;

export default function ResizeHandles() {
  const startResize = useCallback(async (e, direction) => {
    if (e.button !== 0) return;
    e.preventDefault();
    e.stopPropagation();

    const dirMap = {
      w: 1,  // Left
      e: 2,  // Right
      n: 3,  // Top
      nw: 4, // Top-Left
      ne: 5, // Top-Right
      s: 6,  // Bottom
      sw: 7, // Bottom-Left
      se: 8, // Bottom-Right
    };

    let initialRect = null;
    try {
      initialRect = await callDesktop('get_window_rect');
    } catch {}

    const startX = e.screenX;
    const startY = e.screenY;

    if (!initialRect) {
      if (dirMap[direction]) {
        callDesktop('start_resize', dirMap[direction]);
      }
      return;
    }

    const { left, top, right, bottom } = initialRect;
    const initialWidth = right - left;
    const initialHeight = bottom - top;

    const onMouseMove = (moveEvt) => {
      const dx = moveEvt.screenX - startX;
      const dy = moveEvt.screenY - startY;

      let newX = left;
      let newY = top;
      let newW = initialWidth;
      let newH = initialHeight;

      if (direction.includes('e')) {
        newW = Math.max(MIN_WIDTH, initialWidth + dx);
      }
      if (direction.includes('s')) {
        newH = Math.max(MIN_HEIGHT, initialHeight + dy);
      }
      if (direction.includes('w')) {
        const potentialW = initialWidth - dx;
        if (potentialW >= MIN_WIDTH) {
          newX = left + dx;
          newW = potentialW;
        } else {
          newW = MIN_WIDTH;
          newX = right - MIN_WIDTH;
        }
      }
      if (direction.includes('n')) {
        const potentialH = initialHeight - dy;
        if (potentialH >= MIN_HEIGHT) {
          newY = top + dy;
          newH = potentialH;
        } else {
          newH = MIN_HEIGHT;
          newY = bottom - MIN_HEIGHT;
        }
      }

      callDesktop('set_window_rect', Math.round(newX), Math.round(newY), Math.round(newW), Math.round(newH));
    };

    const onMouseUp = () => {
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
    };

    document.body.style.userSelect = 'none';
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
  }, []);

  const handles = [
    { dir: 'n', style: { top: 0, left: 8, right: 8, height: 6, cursor: 'ns-resize' } },
    { dir: 's', style: { bottom: 0, left: 8, right: 8, height: 6, cursor: 'ns-resize' } },
    { dir: 'w', style: { top: 8, bottom: 8, left: 0, width: 6, cursor: 'ew-resize' } },
    { dir: 'e', style: { top: 8, bottom: 8, right: 0, width: 6, cursor: 'ew-resize' } },
    { dir: 'nw', style: { top: 0, left: 0, width: 10, height: 10, cursor: 'nwse-resize' } },
    { dir: 'ne', style: { top: 0, right: 0, width: 10, height: 10, cursor: 'nesw-resize' } },
    { dir: 'sw', style: { bottom: 0, left: 0, width: 10, height: 10, cursor: 'nesw-resize' } },
    { dir: 'se', style: { bottom: 0, right: 0, width: 10, height: 10, cursor: 'nwse-resize' } },
  ];

  return (
    <div className="window-resize-handles" style={{ pointerEvents: 'none', position: 'fixed', inset: 0, zIndex: 999999 }}>
      {handles.map(({ dir, style }) => (
        <div
          key={dir}
          style={{ position: 'absolute', pointerEvents: 'auto', ...style }}
          onMouseDown={(e) => startResize(e, dir)}
        />
      ))}
    </div>
  );
}
