import { test } from 'node:test'
import assert from 'node:assert/strict'
import { File } from 'node:buffer'
import { readFileSync } from 'node:fs'
import {
  AI_PHOTO_MAX_BYTES, AI_PHOTO_TARGET_BYTES, AI_PHOTO_MAX_SOURCE_BYTES,
  photoDisposition, prepareMealPhoto, photoSizeLabel, scaledPhotoDimensions,
  paintPrivateMealPhoto, remapPrivateMealMasks,
} from '../src/utils/mealPhoto.ts'

test('all accepted images are redrawn, including those below 3MB', () => {
  for (const type of ['image/jpeg', 'image/png', 'image/webp']) {
    assert.equal(photoDisposition({ name: 'meal.jpg', type, size: 90_000 }), 'convert')
    assert.equal(photoDisposition({ name: 'meal.jpg', type, size: AI_PHOTO_MAX_BYTES }), 'convert')
    assert.equal(photoDisposition({ name: 'meal.jpg', type, size: AI_PHOTO_MAX_BYTES + 1 }), 'convert')
  }
  assert.equal(photoSizeLabel(870069), '0.87 MB')
})

test('iOS HEIC and HEIF photos are converted even when small', () => {
  assert.equal(photoDisposition({ name: 'IMG_1.HEIC', type: 'image/heic', size: 700_000 }), 'convert')
  assert.equal(photoDisposition({ name: 'IMG_1.HEIF', type: '', size: 700_000 }), 'convert')
  assert.equal(photoDisposition({ name: 'IMG_1.JPEG', type: '', size: 700_000 }), 'convert')
})

test('reject unsupported, empty and excessive-size files before image decoding', () => {
  assert.throws(() => photoDisposition({ name: 'x.gif', type: 'image/gif', size: 100 }), /JPG/)
  assert.throws(() => photoDisposition({ name: 'x.jpg', type: 'image/jpeg', size: 0 }), /为空/)
  assert.throws(() => photoDisposition({
    name: 'x.jpg', type: 'image/jpeg', size: AI_PHOTO_MAX_SOURCE_BYTES + 1,
  }), /25 MB/)
  assert.deepEqual(scaledPhotoDimensions(4032, 3024, 2048), { width: 2048, height: 1536 })
  assert.deepEqual(scaledPhotoDimensions(1080, 810, 2048), { width: 1080, height: 810 })
  assert.throws(() => scaledPhotoDimensions(0, 500, 2048), /尺寸/)
})

test('a small original is never uploaded unmodified, even with EXIF or private filename', async () => {
  const origImage = globalThis.Image
  const origDocument = globalThis.document
  const origFile = globalThis.File
  const origCreate = URL.createObjectURL
  const origRevoke = URL.revokeObjectURL
  globalThis.File = File
  globalThis.Image = class {
    naturalWidth = 1600
    naturalHeight = 1200
    set src(value) { queueMicrotask(() => this.onload?.()) }
  }
  globalThis.document = {
    createElement: () => ({
      width: 0, height: 0,
      getContext: () => ({ drawImage: () => {}, fillRect: () => {},
                          set fillStyle(value) {} }),
      toBlob: callback => callback(new Blob([new Uint8Array(510_000)], { type: 'image/jpeg' })),
    }),
  }
  let revoked = false
  URL.createObjectURL = () => 'blob:private-original'
  URL.revokeObjectURL = () => { revoked = true }
  try {
    const original = new File([new Uint8Array(720_000)], '张三-13800138000.jpeg',
      { type: 'image/jpeg' })
    const result = await prepareMealPhoto(original)
    assert.notEqual(result.file, original)
    assert.equal(result.file.name, 'prp-meal.jpg')
    assert.equal(result.file.type, 'image/jpeg')
    assert.equal(result.file.size, 510_000)
    assert.equal(result.compressed, true)
    assert.equal(revoked, true)
  } finally {
    globalThis.Image = origImage
    globalThis.document = origDocument
    globalThis.File = origFile
    URL.createObjectURL = origCreate
    URL.revokeObjectURL = origRevoke
  }
})

test('oversize image is locally converted to a real JPEG file below POST limit', async () => {
  const origImage = globalThis.Image
  const origDocument = globalThis.document
  const origFile = globalThis.File
  const origCreate = URL.createObjectURL
  const origRevoke = URL.revokeObjectURL
  const draws = []
  let revoked = false
  globalThis.File = File
  globalThis.Image = class {
    naturalWidth = 4032
    naturalHeight = 3024
    set src(value) { queueMicrotask(() => this.onload?.()) }
  }
  globalThis.document = {
    createElement: (tag) => {
      assert.equal(tag, 'canvas')
      return {
        width: 0, height: 0,
        getContext: () => ({
          fillRect: () => {},
          drawImage: (...args) => draws.push(args),
          set fillStyle(value) {},
        }),
        toBlob: (callback, mime, quality) => {
          assert.equal(mime, 'image/jpeg')
          const count = quality >= 0.88 ? 3_200_000 : 2_400_000
          callback(new Blob([new Uint8Array(count)], { type: mime }))
        },
      }
    },
  }
  URL.createObjectURL = () => 'blob:local-test'
  URL.revokeObjectURL = (url) => { assert.equal(url, 'blob:local-test'); revoked = true }
  try {
    const source = new File([new Uint8Array(3_100_000)], 'IMG_0001.jpg', { type: 'image/jpeg' })
    const result = await prepareMealPhoto(source)
    assert.equal(result.compressed, true)
    assert.equal(result.originalBytes, 3_100_000)
    assert.equal(result.file.name, 'prp-meal.jpg')
    assert.equal(result.file.type, 'image/jpeg')
    assert.ok(result.file.size <= AI_PHOTO_TARGET_BYTES)
    assert.ok(result.file.size <= AI_PHOTO_MAX_BYTES)
    assert.ok(draws.length > 0)
    assert.equal(revoked, true)
  } finally {
    globalThis.Image = origImage
    globalThis.document = origDocument
    globalThis.File = origFile
    URL.createObjectURL = origCreate
    URL.revokeObjectURL = origRevoke
  }
})

test('opaque black masks are applied to the cropped pixels before JPEG encode', () => {
  const calls = []
  let color = ''
  const canvas = {
    set fillStyle(next) { color = next },
    fillRect: (...args) => calls.push({ op: 'fill', color, args }),
    drawImage: (...args) => calls.push({ op: 'source', args }),
  }
  const photo = { localOnly: true }
  paintPrivateMealPhoto(
    canvas, photo, 1200, 800, 600, 400,
    { x: 0.1, y: 0.25, width: 0.5, height: 0.5 },
    [{ x: 0.25, y: 0.1, width: 0.3, height: 0.15 }],
  )
  assert.deepEqual(calls, [
    { op: 'fill', color: '#ffffff', args: [0, 0, 600, 400] },
    { op: 'source', args: [photo, 120, 200, 600, 400, 0, 0, 600, 400] },
    { op: 'fill', color: '#000000', args: [148, 38, 184, 64] },
  ])
})

test('invalid crop and mask geometry are rejected rather than exporting unmasked pixels', () => {
  const canvas = { set fillStyle(_) {}, fillRect: () => {}, drawImage: () => {} }
  const full = { x: 0, y: 0, width: 1, height: 1 }
  assert.throws(() => paintPrivateMealPhoto(canvas, {}, 100, 100, 100, 100,
    { x: 0.5, y: 0.5, width: 0.75, height: 0.75 }, []), /区域无效/)
  assert.throws(() => paintPrivateMealPhoto(canvas, {}, 100, 100, 100, 100,
    full, [{ x: -0.1, y: 0, width: 0.25, height: 0.2 }]), /区域无效/)
  assert.throws(() => paintPrivateMealPhoto(canvas, {}, 100, 100, 100, 100,
    full, new Array(41).fill(full)), /区域无效/)
})

test('both upload entrypoints require explicit local privacy-review confirmation', () => {
  const chat = readFileSync(new URL('../src/views/ChatView.vue', import.meta.url), 'utf8')
  const recorder = readFileSync(new URL('../src/components/wellness/WellnessAiRecorder.vue',
    import.meta.url), 'utf8')
  const editor = readFileSync(new URL('../src/components/wellness/MealPhotoPrivacyEditor.vue',
    import.meta.url), 'utf8')
  for (const view of [chat, recorder]) {
    assert.match(view, /MealPhotoPrivacyEditor/)
    assert.match(view, /photoPrivacyOpen/)
    assert.match(view, /@prepared="photoPrepared"/)
    assert.doesNotMatch(view, /(?:chatPhoto|file)\.value\s*=\s*source/)
  }
  assert.match(editor, /paintPrivateMealPhoto\(context, image/)
  assert.match(editor, /prepareMealPhoto\(rendered\)/)
  assert.match(editor, /emit\('prepared', prepared\.file\)/)
})

test('cropping after redaction retains intersecting masks and discards only outside ones', () => {
  const crop = { x: 0.25, y: 0.2, width: 0.5, height: 0.5 }
  const result = remapPrivateMealMasks(crop, [
    { x: 0.4, y: 0.3, width: 0.2, height: 0.3 },
    { x: 0, y: 0, width: 0.1, height: 0.1 },
    { x: 0.1, y: 0.15, width: 0.2, height: 0.2 },
  ])
  assert.equal(result.length, 2)
  for (const [value, expected] of [
    [result[0].x, 0.3], [result[0].y, 0.2],
    [result[0].width, 0.4], [result[0].height, 0.6],
    [result[1].x, 0], [result[1].y, 0],
    [result[1].width, 0.1], [result[1].height, 0.3],
  ]) assert.ok(Math.abs(value - expected) < 1e-9)
  assert.throws(() => remapPrivateMealMasks(crop,
    [{ x: 0.8, y: 0.9, width: 0.3, height: 0.3 }]), /区域无效/)
})

test('blackout masks fill outward to pixel boundaries and stay opaque at crop edges', () => {
  const calls = []
  let color = ''
  paintPrivateMealPhoto({
    set fillStyle(x) { color = x },
    fillRect: (...args) => calls.push({ color, args }),
    drawImage: () => {},
  }, {}, 100, 100, 100, 100,
  { x: 0, y: 0, width: 1, height: 1 },
  [{ x: 0, y: 0, width: 0.1, height: 0.1 },
   { x: 0.95, y: 0.95, width: 0.05, height: 0.05 }])
  assert.deepEqual(calls.filter(x => x.color === '#000000'), [
    { color: '#000000', args: [0, 0, 12, 12] },
    { color: '#000000', args: [93, 93, 7, 7] },
  ])
})
