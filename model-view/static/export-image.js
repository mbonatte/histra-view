import * as THREE from 'three';

const MAX_DIMENSION = 8192;

export function exportDimensions(width, height, scale = 3, maximum = MAX_DIMENSION) {
  const baseWidth = Math.max(1, Math.round(Number(width) || 1));
  const baseHeight = Math.max(1, Math.round(Number(height) || 1));
  const requested = Math.max(1, Math.min(6, Number(scale) || 1));
  let outWidth = Math.round(baseWidth * requested);
  let outHeight = Math.round(baseHeight * requested);
  const factor = Math.min(1, maximum / outWidth, maximum / outHeight);
  outWidth = Math.max(1, Math.round(outWidth * factor));
  outHeight = Math.max(1, Math.round(outHeight * factor));
  return { width: outWidth, height: outHeight, scale: outWidth / baseWidth };
}

export function sanitizeFilename(value) {
  return String(value ?? 'view')
    .replace(/[^a-z0-9._-]+/gi, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 120) || 'view';
}

function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function imageFromBlob(blob) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(blob);
    const image = new Image();
    image.onload = () => { URL.revokeObjectURL(url); resolve(image); };
    image.onerror = () => { URL.revokeObjectURL(url); reject(new Error('Unable to decode the exported image.')); };
    image.src = url;
  });
}

function canvasBlob(canvas, type = 'image/png') {
  return new Promise((resolve, reject) => {
    canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error('The browser could not encode the image.')), type);
  });
}

function drawSwatch(ctx, item, x, y, size) {
  if (item.type === 'dot') {
    ctx.beginPath();
    ctx.arc(x + size / 2, y, size * 0.34, 0, Math.PI * 2);
    ctx.fillStyle = item.color || '#ef4444';
    ctx.fill();
    return size;
  }
  if (item.type === 'gradient') {
    const gradient = ctx.createLinearGradient(x, y, x + size, y);
    const colors = item.colors?.length ? item.colors : ['#2b6cb0', '#e6ebf0', '#e64033'];
    colors.forEach((color, index) => gradient.addColorStop(index / Math.max(1, colors.length - 1), color));
    ctx.fillStyle = gradient;
    ctx.fillRect(x, y - 2, size, 4);
    return size;
  }
  ctx.fillStyle = item.color || '#38bdf8';
  ctx.fillRect(x, y - 1.5, size, 3);
  return size;
}

function captionLayout(width, caption) {
  const pad = Math.max(16, Math.round(width * 0.022));
  const titleSize = Math.max(18, Math.round(width * 0.014));
  const bodySize = Math.max(13, Math.round(width * 0.0095));
  const legend = caption.legend || [];
  const titleHeight = titleSize * 1.25;
  const subtitleHeight = caption.subtitle ? bodySize * 1.55 : 0;
  const legendHeight = legend.length ? bodySize * 1.9 : 0;
  return {
    pad, titleSize, bodySize, legend,
    titleHeight, subtitleHeight, legendHeight,
    boxHeight: pad * 2 + titleHeight + subtitleHeight + legendHeight,
  };
}

function drawCaption(ctx, width, height, caption, background, top = null) {
  if (!caption) return 0;
  const layout = captionLayout(width, caption);
  const boxTop = top == null ? height - layout.boxHeight : top;
  const light = background === 'white';
  const strip = light ? 'rgba(255,255,255,0.9)' : 'rgba(9,15,21,0.78)';
  const title = light ? '#18232d' : '#dce9f2';
  const muted = light ? '#4c5d6a' : '#9fb3c2';

  ctx.fillStyle = strip;
  ctx.fillRect(0, boxTop, width, layout.boxHeight);
  ctx.textBaseline = 'top';
  ctx.textAlign = 'left';
  ctx.fillStyle = title;
  ctx.font = `600 ${layout.titleSize}px Inter, ui-sans-serif, system-ui, sans-serif`;
  ctx.fillText(caption.title || '', layout.pad, boxTop + layout.pad, width - layout.pad * 2);
  let y = boxTop + layout.pad + layout.titleHeight;
  if (caption.subtitle) {
    ctx.fillStyle = muted;
    ctx.font = `${layout.bodySize}px ui-monospace, SFMono-Regular, Menlo, monospace`;
    ctx.fillText(caption.subtitle, layout.pad, y, width - layout.pad * 2);
    y += layout.subtitleHeight;
  }
  if (layout.legend.length) {
    let x = layout.pad;
    const swatch = Math.round(layout.bodySize * 1.8);
    const midpoint = y + layout.bodySize * 0.8;
    ctx.font = `${layout.bodySize}px ui-sans-serif, system-ui, sans-serif`;
    for (const item of layout.legend) {
      const used = drawSwatch(ctx, item, x, midpoint, swatch);
      x += used + Math.round(layout.bodySize * 0.45);
      ctx.fillStyle = muted;
      ctx.fillText(item.label || '', x, y, width);
      x += Math.round(ctx.measureText(item.label || '').width + layout.bodySize * 1.5);
      if (x > width - layout.pad) break;
    }
  }
  return layout.boxHeight;
}

function imageCanvas(source, width, height) {
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('The browser could not create an export canvas.');
  ctx.drawImage(source, 0, 0);
  return { canvas, ctx };
}

function contentBounds(ctx, width, height, background) {
  const data = ctx.getImageData(0, 0, width, height).data;
  const base = background === 'white' ? [255, 255, 255] : background === 'screen' ? [17, 24, 32] : null;
  let minX = width, minY = height, maxX = -1, maxY = -1;
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const i = (y * width + x) * 4;
      const delta = base
        ? Math.max(Math.abs(data[i] - base[0]), Math.abs(data[i + 1] - base[1]), Math.abs(data[i + 2] - base[2]))
        : data[i + 3];
      if (delta > 10) {
        if (x < minX) minX = x;
        if (x > maxX) maxX = x;
        if (y < minY) minY = y;
        if (y > maxY) maxY = y;
      }
    }
  }
  if (maxX < minX || maxY < minY) return null;
  const margin = Math.max(8, Math.round(Math.min(width, height) * 0.035));
  return {
    x: Math.max(0, minX - margin),
    y: Math.max(0, minY - margin),
    width: Math.min(width, maxX + margin + 1) - Math.max(0, minX - margin),
    height: Math.min(height, maxY + margin + 1) - Math.max(0, minY - margin),
  };
}

function croppedCanvas(source, width, height, background) {
  const full = imageCanvas(source, width, height);
  const bounds = contentBounds(full.ctx, width, height, background);
  if (!bounds || bounds.width < width * 0.1 || bounds.height < height * 0.1) return full.canvas;
  const output = document.createElement('canvas');
  output.width = bounds.width;
  output.height = bounds.height;
  const ctx = output.getContext('2d');
  if (!ctx) throw new Error('The browser could not create an export canvas.');
  ctx.drawImage(full.canvas, bounds.x, bounds.y, bounds.width, bounds.height, 0, 0, bounds.width, bounds.height);
  return output;
}

function restore(viewer, saved) {
  const { renderer, scene } = viewer;
  renderer.setPixelRatio(saved.pixelRatio);
  renderer.setSize(saved.width, saved.height, false);
  if (saved.cameraAspect !== undefined) {
    viewer.camera.aspect = saved.cameraAspect;
    viewer.camera.updateProjectionMatrix();
  }
  scene.background = saved.background;
  renderer.setClearColor(saved.clearColor, saved.clearAlpha);
  if (viewer.axes) viewer.axes.visible = saved.axes;
  if (viewer.grid) viewer.grid.visible = saved.grid;
  viewer.resize();
  viewer.needsRender = true;
}

export async function exportViewerPng(viewer, options = {}) {
  const renderer = viewer?.renderer;
  const scene = viewer?.scene;
  const camera = viewer?.camera;
  if (!renderer || !scene || !camera || !renderer.domElement) {
    throw new Error('The 3D view is not ready for export.');
  }
  const container = viewer.container;
  const baseWidth = Math.max(1, container?.clientWidth || renderer.domElement.clientWidth || renderer.domElement.width);
  const baseHeight = Math.max(1, container?.clientHeight || renderer.domElement.clientHeight || renderer.domElement.height);
  const dimensions = exportDimensions(baseWidth, baseHeight, options.scale ?? 3);
  const oldSize = renderer.getSize(new THREE.Vector2());
  const saved = {
    pixelRatio: renderer.getPixelRatio(),
    width: oldSize.x,
    height: oldSize.y,
    background: scene.background,
    clearColor: renderer.getClearColor(new THREE.Color()),
    clearAlpha: renderer.getClearAlpha(),
    cameraAspect: camera.isPerspectiveCamera ? camera.aspect : undefined,
    axes: viewer.axes?.visible,
    grid: viewer.grid?.visible,
  };
  try {
    renderer.setPixelRatio(1);
    renderer.setSize(dimensions.width, dimensions.height, false);
    if (viewer.perspCamera) {
      viewer.perspCamera.aspect = dimensions.width / dimensions.height;
      viewer.perspCamera.updateProjectionMatrix();
    }
    if (viewer._updateOrthoFrustum) viewer._updateOrthoFrustum(dimensions.width / dimensions.height);
    if (camera.isPerspectiveCamera) {
      camera.aspect = dimensions.width / dimensions.height;
      camera.updateProjectionMatrix();
    }
    const background = options.background || 'white';
    if (background === 'white') {
      scene.background = new THREE.Color(0xffffff);
      renderer.setClearColor(0xffffff, 1);
    } else if (background === 'transparent') {
      scene.background = null;
      renderer.setClearColor(0x000000, 0);
    }
    if (options.axes === false) {
      if (viewer.axes) viewer.axes.visible = false;
      if (viewer.grid) viewer.grid.visible = false;
    }
    renderer.render(scene, camera);
    const rendered = await canvasBlob(renderer.domElement);
    const source = await imageFromBlob(rendered);
    const crop = options.crop !== false;
    const image = crop
      ? croppedCanvas(source, dimensions.width, dimensions.height, background)
      : imageCanvas(source, dimensions.width, dimensions.height).canvas;
    const layout = options.caption ? captionLayout(image.width, options.caption) : null;
    const output = document.createElement('canvas');
    output.width = image.width;
    output.height = image.height + (layout && crop ? layout.boxHeight : 0);
    const ctx = output.getContext('2d');
    if (!ctx) throw new Error('The browser could not create an export canvas.');
    if (background !== 'transparent') {
      ctx.fillStyle = background === 'white' ? '#ffffff' : '#111820';
      ctx.fillRect(0, 0, output.width, output.height);
    }
    ctx.drawImage(image, 0, 0);
    if (options.caption) {
      drawCaption(ctx, output.width, output.height, options.caption, background, crop ? image.height : null);
    }
    const blob = await canvasBlob(output);
    return { blob, width: output.width, height: output.height };
  } finally {
    restore(viewer, saved);
  }
}

export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = 'noopener';
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  void delay(1000).then(() => URL.revokeObjectURL(url));
}
