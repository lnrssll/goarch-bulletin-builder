#import "build_path.typ": date, build_path

#set page(
  paper: "a6",
  margin: (x: 1.0cm, y: 1.0cm),
)

#let manual_data = yaml(build_path + "manual.yaml")

#let epistle_data = yaml(build_path + "epistle.yaml")
#let gospel_data = yaml(build_path + "gospel.yaml")
#let feed_data = yaml(build_path + "feed.yaml")
#let dcs_data = yaml(build_path + "digital_chant_stand.yaml")

#let size = 10pt * (feed_data.text_size_factor / 100)
#set text(size: size)

#let image_path = build_path + feed_data.icon_filename

#align(top + center)[
  #title[#(feed_data.lectionary_title)]
  #if feed_data.icon_title.len() > 0 [
    #text(size: size)[_On #feed_data.formatted_date, we commemorate_ \ #feed_data.icon_title]
  ] else [
    == #feed_data.formatted_date
  ]
]

#align(center + horizon)[
  #image(image_path, height: 50%)
]

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

#pagebreak()

=== The Prokeimenon

#text[
  #set par(
    hanging-indent: 1em,
    spacing: .8em
  )
  #epistle_data.prokeimenon
  
  *Verse:* #epistle_data.verse
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

#reading_block(epistle_data)

#if feed_data.alleluia_page_break [
  #pagebreak()
]

=== The Alleluia

#for stichoi in dcs_data.alleluia [
  #set par(
    hanging-indent: 1em,
    spacing: .8em
  )
  #stichoi
]

#if feed_data.gospel_page_break [
  #pagebreak()
]

#reading_block(gospel_data)

#pagebreak()

#include "bulletin_back.typ"
