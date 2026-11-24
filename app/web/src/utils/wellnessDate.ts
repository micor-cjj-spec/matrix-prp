/** Resolve a health business day in the user's configured timezone, not the device timezone. */
export function dateInTimeZone(timeZone: string, now: Date = new Date()): string {
  try {
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone, year: 'numeric', month: '2-digit', day: '2-digit',
    }).formatToParts(now)
    const fields = new Map(parts.map(part => [part.type, part.value]))
    const year = fields.get('year')
    const month = fields.get('month')
    const day = fields.get('day')
    if (!year || !month || !day) throw new RangeError('Missing date parts')
    return `${year}-${month}-${day}`
  } catch {
    // Fail closed to the existing device-date UI behavior when profile data is invalid.
    return [now.getFullYear(), String(now.getMonth() + 1).padStart(2, '0'),
      String(now.getDate()).padStart(2, '0')].join('-')
  }
}
