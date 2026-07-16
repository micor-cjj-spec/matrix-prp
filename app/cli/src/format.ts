export function printJson(value: unknown) {
  console.log(JSON.stringify(value, null, 2))
}

export function printItems<T>(items: T[], emptyMessage: string, render: (item: T) => string) {
  if (items.length === 0) {
    console.log(emptyMessage)
    return
  }
  for (const item of items) {
    console.log(render(item))
  }
}
