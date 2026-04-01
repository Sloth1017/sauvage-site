import React, { useEffect, useRef } from 'react';

export default function Grainient({
  color1 = "#f6f1e6",
  color2 = "#614e42",
  color3 = "#f6f1e6",
  timeSpeed = 0.25,
  colorBalance = 0,
  warpStrength = 1,
  warpFrequency = 5,
  warpSpeed = 2,
  warpAmplitude = 50,
  blendAngle = 0,
  blendSoftness = 0.05,
  rotationAmount = 500,
  noiseScale = 2,
  grainAmount = 0.1,
  grainScale = 2,
  grainAnimated = false,
  contrast = 1.5,
  gamma = 1,
  saturation = 1,
  centerX = 0,
  centerY = 0,
  zoom = 0.9,
}) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    let animationId;
    let time = 0;

    const hexToRgb = (hex) => {
      const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
      return result ? [
        parseInt(result[1], 16),
        parseInt(result[2], 16),
        parseInt(result[3], 16)
      ] : [246, 241, 230];
    };

    const rgb1 = hexToRgb(color1);
    const rgb2 = hexToRgb(color2);
    const rgb3 = hexToRgb(color3);

    const perlin = (x, y, z) => {
      const xi = Math.floor(x) & 255;
      const yi = Math.floor(y) & 255;
      const zi = Math.floor(z) & 255;
      const xf = x - Math.floor(x);
      const yf = y - Math.floor(y);
      const zf = z - Math.floor(z);
      
      const u = xf * xf * (3 - 2 * xf);
      const v = yf * yf * (3 - 2 * yf);
      const w = zf * zf * (3 - 2 * zf);
      
      return Math.sin((xi + yi + zi) * 0.1) * (1 - u) * (1 - v) * (1 - w) +
             Math.cos((xi + yi + zi) * 0.1) * u * v * w;
    };

    const animate = () => {
      canvas.width = canvas.offsetWidth;
      canvas.height = canvas.offsetHeight;

      const imageData = ctx.createImageData(canvas.width, canvas.height);
      const data = imageData.data;

      time += timeSpeed * 0.01;

      for (let y = 0; y < canvas.height; y++) {
        for (let x = 0; x < canvas.width; x++) {
          const nx = (x / canvas.width - 0.5 + centerX) * zoom;
          const ny = (y / canvas.height - 0.5 + centerY) * zoom;

          const warpX = nx + perlin(nx * warpFrequency, ny * warpFrequency, time * warpSpeed) * warpAmplitude * warpStrength * 0.001;
          const warpY = ny + perlin(nx * warpFrequency + 10, ny * warpFrequency + 10, time * warpSpeed) * warpAmplitude * warpStrength * 0.001;

          const noise = perlin(warpX * noiseScale, warpY * noiseScale, time * 0.5);
          const t = (Math.sin(blendAngle * Math.PI / 180) * warpX + Math.cos(blendAngle * Math.PI / 180) * warpY) * 0.5 + 0.5 + colorBalance;
          
          let r, g, b;
          if (t < 0.5) {
            const mix = t * 2;
            r = rgb1[0] * (1 - mix) + rgb2[0] * mix;
            g = rgb1[1] * (1 - mix) + rgb2[1] * mix;
            b = rgb1[2] * (1 - mix) + rgb2[2] * mix;
          } else {
            const mix = (t - 0.5) * 2;
            r = rgb2[0] * (1 - mix) + rgb3[0] * mix;
            g = rgb2[1] * (1 - mix) + rgb3[1] * mix;
            b = rgb2[2] * (1 - mix) + rgb3[2] * mix;
          }

          r = Math.pow(r / 255, 1 / gamma) * 255 * contrast;
          g = Math.pow(g / 255, 1 / gamma) * 255 * contrast;
          b = Math.pow(b / 255, 1 / gamma) * 255 * contrast;

          const gray = (r + g + b) / 3;
          r = gray + (r - gray) * saturation;
          g = gray + (g - gray) * saturation;
          b = gray + (b - gray) * saturation;

          let grain = 0;
          if (grainAmount > 0) {
            grain = (Math.random() - 0.5) * 2 * grainAmount * 255;
            if (!grainAnimated) grain *= 0.3;
          }

          const idx = (y * canvas.width + x) * 4;
          data[idx] = Math.min(255, Math.max(0, r + grain));
          data[idx + 1] = Math.min(255, Math.max(0, g + grain));
          data[idx + 2] = Math.min(255, Math.max(0, b + grain));
          data[idx + 3] = 255;
        }
      }

      ctx.putImageData(imageData, 0, 0);
      animationId = requestAnimationFrame(animate);
    };

    animate();
    return () => cancelAnimationFrame(animationId);
  }, [color1, color2, color3, timeSpeed, colorBalance, warpStrength, warpFrequency, warpSpeed, warpAmplitude, blendAngle, blendSoftness, rotationAmount, noiseScale, grainAmount, grainScale, grainAnimated, contrast, gamma, saturation, centerX, centerY, zoom]);

  return (
    <canvas
      ref={canvasRef}
      style={{
        width: '100%',
        height: '100%',
        display: 'block',
      }}
    />
  );
}
