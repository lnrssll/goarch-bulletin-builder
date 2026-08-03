#import "build_path.typ": date, build_path

#let manual_data = yaml(build_path + "manual.yaml")

#let epistle_data = yaml(build_path + "epistle.yaml")
#let gospel_data = yaml(build_path + "gospel.yaml")
#let feed_data = yaml(build_path + "feed.yaml")
#let dcs_data = yaml(build_path + "digital_chant_stand.yaml")

#let size = 10pt * (feed_data.text_size_factor / 100)

#let image_path = build_path + feed_data.icon_filename

////////////////////////////////////////////////////////////////////////////////
// PAGE CONTENT
//
// These are exposed as plain content (rather than being emitted directly)
// so that other documents -- e.g. booklet.typ -- can #import and re-lay
// them out without depending on this file's own page setup below.
////////////////////////////////////////////////////////////////////////////////

#let front_page = [
  #set text(size: size)

  #align(center + horizon)[
    #title[#(feed_data.lectionary_title)]
    #if feed_data.icon_title.len() > 0 [
      #text(size: size)[_On #feed_data.formatted_date, we commemorate_ \ #feed_data.icon_title]
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
      first-line-indent: 1em,
      spacing: 0.65em,
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
      hanging-indent: 1em,
      spacing: .8em
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
      hanging-indent: 1em,
      spacing: .8em
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
  paper: "a6",
  margin: (x: 1.0cm, y: 1.0cm),
)

#front_page
#pagebreak()
#readings()
#pagebreak()
#back_page
