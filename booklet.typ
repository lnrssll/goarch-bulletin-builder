// Booklet imposition for bulletin.typ.
//
// Takes the same content bulletin.typ would print one A6 page at a time,
// and re-lays it out two-up on A5-landscape sheets. Folded in half, an A5
// landscape sheet becomes a pair of A6 pages -- the sheet's inner margins
// are doubled to `gutter` below so each half still gets the same 1cm
// margin on every side that the standalone A6 page gets.
//
// Print both sheets double-sided (flip on the long edge), then fold and
// nest them: sheet 1 is the outside of the booklet (back cover / front
// cover), sheet 2 is the inside spread (page 2 / page 3).
//
// This file only knows how to arrange content into a spread -- it imports
// the actual pages from bulletin.typ, so any future bulletin content
// changes are picked up automatically.

#import "bulletin.typ": front_page, back_page, readings

#set page(
  paper: "a5",
  flipped: true,
  margin: (x: 1.0cm, y: 1.0cm),
)

#let spread(left, right, gutter: 2cm) = columns(2, gutter: gutter)[
  #left
  #colbreak()
  #right
]

// Sheet 1: outside of the booklet.
#spread(back_page, front_page)

#pagebreak()

// Sheet 2: inside spread. The readings flow across both columns exactly
// as they would flow across pages 2 and 3 of the standalone bulletin,
// using colbreak() instead of pagebreak() wherever a forced break is
// needed.
#columns(2, gutter: 2cm)[
  #readings(sep: colbreak)
]
