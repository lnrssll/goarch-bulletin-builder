#import "inputs.typ": sunday_path, settings_path, parish

#let manual_data = yaml(sunday_path + "manual.yaml")

#let epistle_data = yaml(sunday_path + "epistle.yaml")
#let gospel_data = yaml(sunday_path + "gospel.yaml")
#let feed_data = yaml(sunday_path + "feed.yaml")
#let dcs_data = yaml(sunday_path + "digital_chant_stand.yaml")

#let layout = yaml("data/layout.yaml")
#let hymn_catalog = yaml("data/hymns.yaml")

#let size = layout.text.base_size_pt * 1pt * (feed_data.text_size_factor / 100)

////////////////////////////////////////////////////////////////////////////////
// PAGE CONTENT
//
// These are exposed as plain content (rather than being emitted directly)
// so that other documents -- e.g. booklet.typ -- can #import and re-lay
// them out without depending on this file's own page setup below.
////////////////////////////////////////////////////////////////////////////////

// The catalog's short form for one of its hymns, otherwise the abbreviations.
#let short_title(title) = {
  let entry = hymn_catalog.hymns.find(hymn => lower(hymn.title) == lower(title))
  if entry != none and "short" in entry { return entry.short }
  let short = title
  for (word, abbreviation) in hymn_catalog.abbreviations {
    short = short.replace(regex("(?i)\\b" + word + "\\b"), abbreviation)
  }
  short
}

// Each title in full if it fits on one line next to the widest mode and page.
#let hymn_cells(hymns, width) = {
  let inset = 5pt
  let modes = hymns.map(it => if it.mode != none { emph[Mode #it.mode] })
  let pages = hymns.map(it => emph(it.page))
  let widest(cells) = calc.max(0pt, ..cells.map(cell => measure(cell).width))
  let title_width = width - widest(modes) - widest(pages) - 6 * inset
  hymns.zip(modes, pages).map(((it, mode, page)) => {
    let title = str(it.title)
    if measure(title).width > title_width { title = short_title(title) }
    ([#title#metadata(title)<hymn-title>], mode, page)
  }).flatten()
}

// The logo at `width`, or at `max_height` if it would be taller than that.
#let logo(width, max_height) = std.layout(size => {
  let wide = image("/" + parish.logo, width: width)
  if measure(wide, width: size.width).height > max_height {
    image("/" + parish.logo, height: max_height)
  } else {
    wide
  }
})

#let front_page = [
  #set text(size: 10pt)

  #align(center + top)[
    #logo(80%, 25mm)
  ]

  #align(center + horizon)[
    #title[#(feed_data.lectionary_title)]
    #if feed_data.icon_title.len() > 0 [
      #text[#emph(parish.commemorate.replace("{date}", feed_data.formatted_date)) \ #feed_data.icon_title]
    ] else [
      == #feed_data.formatted_date
    ]
  ]

  #set table(
    stroke: none,
    align: left
  )

  #align(bottom + center)[
    === #parish.hymns_heading

    #text(size: 8pt)[
      #std.layout(size => table(
        columns: 3,
        inset: 5pt,
        ..hymn_cells(manual_data.dismissal_hymns, size.width)
      ))
    ]
  ]
]

#let reading_block(data) = [
  === #parish.reading_heading #(data.book)
  #emph(data.chapverse)

  #set par(
    first-line-indent: layout.text.indent_em * 1em,
    spacing: layout.text.para_spacing_em * 1em,
  )

  #for paragraph in data.text [
    #paragraph #parbreak()
  ]
]

#let epistle_section = [
  === #parish.prokeimenon_heading

  #text[
    #set par(
      hanging-indent: layout.text.indent_em * 1em,
      spacing: layout.text.verse_spacing_em * 1em
    )
    #epistle_data.prokeimenon

    #strong(parish.verse_label) #epistle_data.verse
  ]

  #reading_block(epistle_data)
]

#let alleluia_section = [
  === #parish.alleluia_heading

  #set par(
    hanging-indent: layout.text.indent_em * 1em,
    spacing: layout.text.verse_spacing_em * 1em
  )

  #for verse in dcs_data.alleluia [
    #verse #parbreak()
  ]
]

#let gospel_section = reading_block(gospel_data)

// Assembles the epistle, alleluia, and gospel readings, inserting a break
// (a #pagebreak by default) at the spots the fetched data says are needed
// to keep each reading on its own page. Pass `sep: colbreak` to lay these
// out across columns instead of pages (see booklet.typ).
#let readings(sep: pagebreak) = [
  #set text(size: size)
  #set par(leading: layout.text.leading_em * 1em)

  #epistle_section

  #if feed_data.alleluia_page_break [
    #sep()
  ]

  #alleluia_section

  #if feed_data.gospel_page_break [
    #sep()
  ]

  #gospel_section
]

#let back_page = include "bulletin_back.typ"

////////////////////////////////////////////////////////////////////////////////
// STANDALONE LAYOUT (single A6 page per sheet)
////////////////////////////////////////////////////////////////////////////////

#set page(
  width: layout.page.width_mm * 1mm,
  height: layout.page.height_mm * 1mm,
  margin: layout.page.margin_mm * 1mm,
)

#front_page
#pagebreak()
#readings()
#pagebreak()
#back_page
