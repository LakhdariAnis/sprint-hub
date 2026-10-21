// Fake data for the panes hubd has no source for yet, shown only in `hubd --demo` (as `hub.demo`).
// Values come from the canvas "Hub UI Screens", mapped to the demo vault's steps (`project/id` keys).
// shortcut: all of it is fixed; each part goes when hubd serves the real thing (Sprints 3, 4 and 7).

export type Check = { ok: boolean; name: string; n?: number }
export type Msg =
  | { kind: 'time'; text: string }
  | { kind: 'me'; text: string }
  | { kind: 'ai'; text: string; tool?: { ok: boolean | null; name: string; arg: string; info: string } }

export const demo = {
  usage: {
    fiveHour: 62, resets: '15:40', week: 38, today: '3h12',
    agents: { cpu: 34, ram: '1.2 GB' },
    system: { cpu: 51, ram: '9.3/16 GB', temp: '62°C' },
  },
  // `when` is the text shown on the right; `done` reminders are struck through.
  reminders: {
    overdue: [{ text: 'Follow up Bosch mail', when: 'Sat' }],
    today: [
      { text: 'Answer Claude on 302', when: 'now' },
      { text: 'Approve 105', when: 'done', done: true },
    ],
    later: [
      { text: 'Call Bosch HR', when: 'Wed 14:00' },
      { text: 'Fraunhofer IPA application', when: 'Nov 3', soon: true },
      { text: 'Compilation TP report', when: 'Nov 10' },
    ],
  },
  // This week, Monday = day 0. `time` is a clock time, or `step` for a planned step; `color` is a theme token.
  week: [
    { day: 0, time: 'step', text: '102 Serve the API', color: 'ac' },
    { day: 1, time: '10:00', text: 'Compilation lab', color: 'm' },
    { day: 2, time: '14:00', text: 'Call Bosch HR', color: 'y' },
    { day: 3, time: 'step', text: '104 Write the docs', color: 'ac' },
    { day: 4, time: '17:00', text: 'Sprint 2 review', color: 'g' },
  ],
  // One running step's chat and its open question.
  chat: {
    step: 'notes/302', session: '5d4c', count: 14,
    messages: [
      { kind: 'time', text: '09:00 · started by hubd' },
      { kind: 'me', text: 'Index the note text so a query finds every section that matches.' },
      {
        kind: 'ai', text: 'I’ll add the index in `src/notes/search.py` and build it from the sections of 301, so a query never reads the files again.',
        tool: { ok: true, name: 'Edit', arg: 'src/notes/search.py', info: '+24 −0' },
      },
      { kind: 'time', text: '09:23' },
      {
        kind: 'ai', text: 'The index is done. One question before the query task (see the checklist). I’m writing the tests now.',
        tool: { ok: null, name: 'Bash', arg: 'uv run pytest -q', info: 'running…' },
      },
    ] as Msg[],
  },
  question: {
    step: 'notes/302', at: '09:23',
    text: 'Should the query wait for the parser in 301?',
    answers: ['Yes, wait for 301', 'No, search plain text'],
  },
  // Per step: lines added/removed on its branch and the check chip shown in Today and Review.
  steps: {
    'demo/103': { add: 120, del: 8, check: { ok: true, name: 'tests', n: 14 } },
    'demo/104': { add: 88, del: 0, check: { ok: false, name: 'ruff' } },
    'notes/301': { add: 64, del: 2, check: { ok: true, name: 'tests', n: 9 } },
  } as Record<string, { add: number; del: number; check: Check }>,
}
