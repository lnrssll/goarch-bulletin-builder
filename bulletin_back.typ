#import "build_path.typ": date, build_path

#set text(size: 9pt)

#let upcoming_services = yaml(build_path + "manual.yaml").upcoming_services

= Welcome

We are pleased to have you join us for today's Divine Liturgy!

In order to receive Holy Communion in the Orthodox Church, one must be baptized and/or chrismated into the Orthodox Church. Whether you are an Orthodox Christian or not, please come forward at the end of the service to receive a blessing and blessed bread, which is offered to everyone. You are also invited to stay for coffee hour.

If you are interested in learning more about the Orthodox Church, please contact one of our visiting priests, using the contact information provided below. Please also add your name and contact information to our visitors book, if you'd like to receive our weekly newsletter for upcoming services and announcements.

=== Upcoming Services

#columns(2, gutter: 20pt)[
  #let mid = calc.ceil(upcoming_services.len() / 2)
  #for (i, service) in upcoming_services.enumerate() [
    #if i == mid { colbreak() }
    #(service.date) - #(service.priest) \
  ]
]

=== Contact Information

#columns(2, gutter: 20pt)[
  #set text(size: 8pt)

  Rev. Fr. Andrew J. Barakos \
  Assumption Church \
  Scottsdale, AZ \

  #("priest@assumptionaz.org") \
  (480) 991-3009

  #colbreak()

  Fr. Timothy Pavlatos \
  Saint Katherine Church \
  Chandler, AZ \

  #("frtimskchurch@gmail.com") \
  (480) 899-3330
]

#v(1fr)

#grid(
  columns: (1fr, auto),
  image("assets/logo.webp", height: 40pt),
  align(horizon)[
    #grid(
      columns: 2,
      gutter: 5pt,
      image("assets/lhoc-qr.png", height: 33pt),
      text(size: 7pt)[lakehavasu \ orthodox \ church.org]
    )
  ]
)
