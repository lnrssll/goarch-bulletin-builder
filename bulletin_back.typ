#import "inputs.typ": sunday_path, settings_path, parish, text_field

#set text(size: 9pt)

#let manual_data = yaml(sunday_path + "manual.yaml")
#let upcoming_services = if type(manual_data) == dictionary { manual_data.at("upcoming_services", default: none) }
#let upcoming_services = if upcoming_services == none { () } else { upcoming_services }

// Name, church and city, then email and phone; empty fields are left out.
#let contact_card(contact) = {
  let lines(..keys) = keys.pos()
    .map(key => contact.at(key, default: none))
    .filter(value => value not in (none, ""))
    .map(str)
    .join(linebreak())
  lines("name", "church", "city")
  parbreak()
  lines("email", "phone")
}

= #parish.welcome_heading

#for paragraph in parish.welcome {
  paragraph
  parbreak()
}

=== #parish.services_heading

#columns(2, gutter: 20pt)[
  #let mid = calc.ceil(upcoming_services.len() / 2)
  #for (i, service) in upcoming_services.enumerate() [
    #if i == mid { colbreak() }
    #text_field(service, "date") - #text_field(service, "priest") \
  ]
]

=== #parish.contacts_heading

#grid(
  columns: (1fr, 1fr),
  column-gutter: 20pt,
  row-gutter: 1.2em,
  ..parish.contacts.map(contact => text(size: 8pt, contact_card(contact))),
)

#v(1fr)

#grid(
  columns: (1fr, auto),
  image("/" + parish.logo, height: 40pt),
  align(horizon)[
    #grid(
      columns: 2,
      gutter: 5pt,
      ..if parish.website != "" { (image(settings_path + "qr.svg", height: 33pt),) } else { () },
      ..if parish.website_lines.len() > 0 { (text(size: 7pt, parish.website_lines.join(linebreak())),) } else { () },
    )
  ]
)
