#let sunday_path = "/state/sundays/" + sys.inputs.date + "/"
#let settings_path = "/state/settings/"

// The defaults, with the church's changes from Settings on top (see parish.py,
// whose ensure() makes sure the second file exists).
#let parish = yaml("/data/parish.yaml") + yaml(settings_path + "parish.yaml")
