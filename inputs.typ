#let sunday_path = "/state/sundays/" + sys.inputs.date + "/"
#let settings_path = "/state/settings/"

// The defaults, with the church's changes from Settings on top (see parish.py,
// whose ensure() makes sure the second file exists).
#let parish = yaml("/data/parish.yaml") + yaml(settings_path + "parish.yaml")

// A field of a hand-editable entry as text: "" when it's missing or empty, so
// `page: 225` or a row without a priest prints rather than stopping the render.
#let text_field(entry, key) = {
  let value = entry.at(key, default: none)
  if value == none { "" } else { str(value) }
}
