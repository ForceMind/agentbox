/** Escape controls and invisible formatting characters before displaying Git names. */
export function visibleGitPath(path: string): string {
  return [...path]
    .map((character) =>
      /[\p{Cc}\p{Cf}\p{Cs}]/u.test(character)
        ? `\\u${(character.codePointAt(0) ?? 0).toString(16).padStart(4, '0')}`
        : character,
    )
    .join('')
}
