const paths = {
  arrow_forward: 'M4 12h16m-6-6 6 6-6 6',
  north_east: 'M6 18 18 6M6 6h12v12',
  south_east: 'm6 6 12 12M6 18h12V6',
  menu: 'M4 6h16M4 12h16M4 18h16',
  close: 'm6 6 12 12M6 18 18 6',
  download: 'M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5',
  upload_file: 'M12 16V4m-5 5 5-5 5 5M4 16v5h16v-5',
  play_arrow: 'm8 5 11 7-11 7Z',
  person: 'M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0ZM4 21v-2a8 8 0 0 1 16 0v2',
  analytics: 'M4 3v18h17M8 16v-5m5 5V7m5 9V4',
  query_stats: 'M3 17 8 11l4 3 8-10M15 4h5v5M4 21h16',
  rule: 'M4 5h10M4 12h7M4 19h10m2-8 2 2 4-4m-4 7 4 4m-4 0 4-4',
  description: 'M5 3h10l4 4v14H5Zm9 0v5h5M8 12h8M8 16h6',
  fact_check: 'M4 3h16v18H4ZM7 8h3m3 0 1 1 3-3M7 15h3m3 0 1 1 3-3',
  table_view: 'M3 4h18v16H3ZM3 10h18M9 10v10M3 15h18',
  insights: 'M3 20 9 12l4 3 8-11M16 4h5v5M3 5h5M5.5 2.5v5',
  auto_awesome: 'm12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5ZM20 2v4m-2-2h4',
  history: 'M3 11a9 9 0 1 1 2 7M3 4v7h7m2-4v6l4 2',
  assessment: 'M5 3h14v18H5Zm4 14v-4m3 4V7m3 10v-7',
  add_circle: 'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM12 8v8m-4-4h8',
  check_circle: 'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-14 0 3 3 7-7',
  radio_button_unchecked: 'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z',
  info: 'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM12 11v6m0-10v.1',
  hourglass_top: 'M6 3h12M6 21h12M7 3v4l10 10v4M17 3v4L7 17v4',
  search: 'M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0Zm-2 5 6 6',
  account_balance: 'm3 8 9-5 9 5ZM3 21h18M5 11v7m7-7v7m7-7v7',
  payments: 'M2 6h20v13H2ZM14 12.5a2 2 0 1 1-4 0 2 2 0 0 1 4 0ZM5 9h1m12 7h1',
}
const aliases = {monitoring:'analytics', task_alt:'check_circle', picture_as_pdf:'description', data_info_alert:'info', home:'assessment'}
export default function Icon({ children }) {
  const name = String(children)
  return <span className="material-symbols-outlined" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d={paths[aliases[name] || name] || paths.insights}/></svg></span>
}
