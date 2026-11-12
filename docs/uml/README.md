# UML diagrams

These diagrams are drawn from the code by `tools/uml_diagrams.py`, so they match it exactly. Open the `.svg` versions in a browser to zoom in; the `.png` versions are for the report.

| Diagram | Shows |
|---|---|
| [0_packages](0_packages.png) | The packages and which ones import which. The four managers never import each other; only `main` (and the web version) use all of them |
| [1_overview](1_overview.png) | Every class by name, grouped by manager, with inheritance, composition and aggregation. The 13 eligibility rules, 4 grant schemes and 4 route groups are each shown as one box |
| [2_controller](2_controller.png) | `Application` (main.py), which owns the four managers, and `Session` |
| [3_io_manager](3_io_manager.png) | `IOManager` and the classes it uses for the terminal, the paper-style output and the screen art |
| [4_ai_manager](4_ai_manager.png) | `AIManager`, the `AIClient` interface and `OpenRouterClient` |
| [5_logic_manager](5_logic_manager.png) | `LogicManager`, `DecisionEngine`, `AccessPolicy`, `RuleConfig`, `PasswordHasher`, `AesGcmCipher` |
| [5b_rules_schemes_adjusters](5b_rules_schemes_adjusters.png) | The polymorphic parts of the Logic Manager: `EligibilityRule`, `GrantScheme` and `DecisionAdjuster` with every subclass |
| [6_data_manager](6_data_manager.png) | `DataManager`, `JsonStore`, `FilenameRules` and the PDF report exporter |
| [7_models](7_models.png) | The shared models: `Proposal`, `ApplicationRecord`, `FileCipher` and the exceptions |
| [8_web](8_web.png) | The Flask version: `WebApplication`, the `RouteGroup` subclasses and the web services |

## How to read them

| Notation | Meaning |
|---|---|
| Hollow triangle | Inheritance (the subclass points to its parent) |
| Filled diamond | Composition: the class at the diamond creates and owns the other one |
| Hollow diamond | Aggregation: the object is handed in from outside (`1..*` = one or more) |
| Dashed arrow | Dependency. «creates»: makes one when needed; «default»: made only when none is handed in; «raises»: raises that exception. Unlabelled: calls its class methods |
| *Italic* name, «abstract» | Abstract class; italic methods must be implemented by subclasses |
| «Exception», «ValueError» | Inherits from that built-in class |
| `+` / `#` / `-` | Public / protected (`_name`) / private (`__name`) |
| <u>underlined</u> | Class attribute, static method or class method |
| `/name` | Property (worked out when read) |
| `show_…() [32 methods]` | A large class's methods grouped by their first word |
| Grey box | A class drawn in full in another diagram |

## Regenerating them

After changing the code, run this from the project folder and commit the updated files:

```
python tools/uml_diagrams.py
```

It needs Graphviz (`winget install graphviz` on Windows, `brew install graphviz` on Mac), then a new terminal so the `dot` command is found.
