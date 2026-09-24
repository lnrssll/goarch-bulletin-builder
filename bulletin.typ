#import "build_path.typ": date, build_path

#let manual_data = yaml(build_path + "manual.yaml")

#let epistle_data = yaml(build_path + "epistle.yaml")
#let gospel_data = yaml(build_path + "gospel.yaml")
#let feed_data = yaml(build_path + "feed.yaml")
#let dcs_data = yaml(build_path + "digital_chant_stand.yaml")

#let layout = yaml("data/layout.yaml")

#let size = layout.text.base_size_pt * 1pt * (feed_data.text_size_factor / 100)

#let image_path = build_path + feed_data.icon_filename

////////////////////////////////////////////////////////////////////////////////
// PAGE CONTENT
//
// These are exposed as plain content (rather than being emitted directly)
// so that other documents -- e.g. booklet.typ -- can #import and re-lay
// them out without depending on this file's own page setup below.
////////////////////////////////////////////////////////////////////////////////

#let front_page = [
  #set text(size: 10pt)

  #align(center + top)[
    #image("assets/logo.webp", width: 80%)
  ]

  #align(center + horizon)[
    #title[#(feed_data.lectionary_title)]
    #if feed_data.icon_title.len() > 0 [
      #text[_On #feed_data.formatted_date, we commemorate_ \ #feed_data.icon_title]
    ] else [
      == #feed_data.formatted_date
    ]
  ]

  // removed images on 08-02-2026
  // #align(center + horizon)[
  //   #image(image_path, height: 50%)
  // ]

  #set table(
    stroke: none,
    align: left
  )

  #align(bottom + center)[
    === Hymns of the Day

    #text(size: 8pt)[
      #table(
        columns: 3,
        ..manual_data.dismissal_hymns.map(it => (it.title, emph[Mode #it.mode], emph(it.page))).flatten()
      )
    ]
  ]
]

#let reading_block(data) = [
  === The Reading is from #(data.book)
  #emph(data.chapverse)

  #text(size: size)[
    #set par(
      first-line-indent: layout.text.indent_em * 1em,
      spacing: layout.text.para_spacing_em * 1em,
    )

    #for paragraph in data.text [
      #paragraph #parbreak()
    ]
  ]
]

#let epistle_section = [
  === The Prokeimenon

  #text[
    #set par(
      hanging-indent: layout.text.indent_em * 1em,
      spacing: layout.text.verse_spacing_em * 1em
    )
    #epistle_data.prokeimenon

    *Verse:* #epistle_data.verse
  ]

  #reading_block(epistle_data)
]

#let alleluia_section = [
  === The Alleluia

  #for stichoi in dcs_data.alleluia [
    #set par(
      hanging-indent: layout.text.indent_em * 1em,
      spacing: layout.text.verse_spacing_em * 1em
    )
    #stichoi
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
