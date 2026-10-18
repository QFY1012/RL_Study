// The name run.mjs gives a page's directory under <out-root>, and plain-site.mjs its files: the host
// for a home page, the host and path for a page deeper in a site (pudding.cool_2025_04_birthday-effect).
export const pageName = (url) => {
  const u = new URL(url)
  return [u.hostname.replace(/^www\./, ""), ...u.pathname.split("/").filter(Boolean)].join("_")
}
