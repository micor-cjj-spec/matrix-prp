import { test } from 'node:test'
import assert from 'node:assert/strict'
import { File } from 'node:buffer'
import {
  AI_PHOTO_MAX_BYTES, AI_PHOTO_TARGET_BYTES, AI_PHOTO_MAX_SOURCE_BYTES,
  photoDisposition, prepareMealPhoto, photoSizeLabel, scaledPhotoDimensions,
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
