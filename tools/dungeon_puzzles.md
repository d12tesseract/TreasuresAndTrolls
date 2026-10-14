# Fifty Random Dungeon Puzzles

**WARNING: TM ONLY - CONTAINS SPOILERS**

This document conatins puzzles meant to be seen ONLY by a GM, including 
solutions.  If players see this ahead of time it would spoil the puzzle

The [dungeon generator](generate_dungeon_map.md#random-puzzles-and-progression-gates)
can place these puzzles automatically, create gated passages, relocate the
best loot, and key required items to reachable encounter areas. Its generated
TM key overrides the illustrative locations and exit destinations below.
Multiple passage puzzles guard independent reward branches, never a nested
sequence; selected multiple exits can lead down from separate branches.
Keep this catalog beside `dungeon_puzzles.py`, which loads its descriptions.

These system-neutral puzzles use classic dungeon and escape-room ideas, with
solutions provided for the game master. Choose by challenge type, or roll 1d6
(reroll a 6) and 1d10: add ten times (the d6 result minus one) to the d10 result.
For manual selection, reroll a puzzle outside its stated dungeon-level range.
Place any required items and their clues before the
barrier they unlock; never hide the only solution behind that same barrier.

For creature encounters, give the players the stated rules through dialogue
and visible clues, rather than requiring a persuasion roll to discover them.
Creative alternatives that meet those rules should work; the listed solutions
are reliable approaches, not mandatory scripts. Characters can describe songs,
memories, and performances without their players having to perform them.

| Roll | Puzzle | Challenge category | Stakes | Outside item |
| --- | --- | --- | --- | --- |
| 1 | The Four Watchers | Deduction and ordering | Unlock a treasure chest | None |
| 2 | The Honest Guardian | Deduction and ordering | Open a passage | None |
| 3 | The Borrowed Sunrise | Light and spatial manipulation | Reveal stairs to a lower level | Sun lens |
| 4 | The Broken King's Shadow | Light and spatial manipulation | Open a hidden treasury | None |
| 5 | The Silent Bell Choir | Sound and sequence | Escape a sealed room | Bronze striker |
| 6 | The Ferryman's Footsteps | Sound and sequence | Cross a flooded shaft | None |
| 7 | The Apothecary's Balance | Measurement and resource manipulation | Unlock a reliquary | None |
| 8 | The Thirsty Door | Measurement and resource manipulation | Drain a passage to a lower level | None |
| 9 | The Pilgrim's Three Offerings | Item matching and exploration | Open an ancient vault | Three shrine tokens |
| 10 | The Absent Jailer | Item matching and exploration | Escape a cell and recover a cache | Brass jailer's badge |
| 11 | The Spirit Who Sold the Door | Spirit bargains and identity | Gain passage without surrendering gear | None |
| 12 | The Name in the Well | Spirit bargains and identity | Raise a bridge and release a spirit | Inscribed name fragment |
| 13 | The Court of Three Ghosts | Spirit bargains and identity | Clear a haunting from a stairway | None |
| 14 | A Lantern for the Forgotten | Spirit bargains and identity | Open a memorial treasure chest | None |
| 15 | The Golem's Literal Orders | Construct logic and commands | Move a guardian off a hatch | None |
| 16 | The Statues That Would Not Bow | Construct logic and commands | Open a royal tomb | None |
| 17 | The Porter with Two Burdens | Construct logic and commands | Raise a dungeon lift | None |
| 18 | The Gardener of Stone | Construct logic and commands | Grow a bridge over a chasm | None |
| 19 | The Troll's Fair Toll | Monster negotiation and perspective | Cross a guarded bridge | None |
| 20 | The Ogre's Supper Guests | Monster negotiation and perspective | Recover a stolen key | None |
| 21 | The Wizard Who Could Not Give | Monster negotiation and perspective | Obtain a magical key | None |
| 22 | The Cleric's Last Blessing | Monster negotiation and perspective | Open a sanctuary | None |
| 23 | The Clockmaker's Borrowed Minute | Time and coordinated action | Escape a repeating room | None |
| 24 | The Duet with Yesterday | Time and coordinated action | Open a sound-sealed door | None |
| 25 | The Guardian Who Walked Backward | Time and coordinated action | Cross a warded gallery | None |
| 26 | The Four Seasons' Audience | Time and coordinated action | Reveal a descending staircase | None |
| 27 | The Golem's Missing Heart | Ritual repair and exploration | Restore a lift and gain an ally | Three heart components |
| 28 | The Feast for an Empty Mouth | Ritual repair and exploration | Open a spirit's treasure cache | Recipe tablet |
| 29 | The Rust Keeper's Hunger | Ritual repair and exploration | Remove a passage-blocking grate | None |
| 30 | The Saint Whose Shadow Lied | Ritual repair and exploration | Remove a ward from a lower level | True oath tablet |
| 31 | The Troll's Three Gem Heaps | Strategy games: Nim | Unlock a gem chest | None |
| 32 | The Fourfold Coin Tithe | Strategy games: Nim | Release an offering coffer | None |
| 33 | The Three-Rail Stone Race | Strategy games: Nim | Lower a passage bridge | None |
| 34 | The Four Sentinels' Retreat | Strategy games: Nim | Unseal the onward gate | None |
| 35 | The Immortal's Last Three Turns | Strategy games: chess | Unlock a chess master's reliquary | None |
| 36 | The Evergreen Spectral Court | Strategy games: chess | Open a monumental gate | None |
| 37 | The Spirit's Short Ladder | Strategy games: Go | Open a pearl casket | None |
| 38 | The Five-Step Dragon Ladder | Strategy games: Go | Clear a warded passage | None |
| 39 | The Twin Tribute of Wythoff | Strategy games: other impartial games | Release a sealed stairway | None |
| 40 | The Ogre's Forbidden Sweet | Strategy games: other impartial games | Unlock an ogre's pantry chest | None |
| 41 | The Fallen Delver's Last Account | Escape rooms: substitution and reading order | Open an adventurer's strongbox | None |
| 42 | The Apprentice's Borrowed Alphabet | Escape rooms: substitution and reading order | Unseal a study passage | None |
| 43 | The Tomb Painter's Backward Farewell | Escape rooms: substitution and reading order | Open a funerary coffer | None |
| 44 | The Owl Librarian's Coordinates | Escape rooms: lookup tables and indexing | Open a forbidden archive | None |
| 45 | The Smuggler's Waterlogged Testament | Escape rooms: lookup tables and indexing | Open a concealed cargo chest | None |
| 46 | The Surveyor's Three Warning Lamps | Escape rooms: binary and signal codes | Release a mine passage gate | None |
| 47 | The Bellmaker's Interrupted Watch | Escape rooms: binary and signal codes | Escape a sealed workshop | None |
| 48 | The Observatory's False Ephemerides | Escape rooms: ordering and extraction | Open an observatory passage | None |
| 49 | The Field Surgeon's Linen Cipher | Escape rooms: ordering and extraction | Open an infirmary medicine chest | None |
| 50 | The Cartographer's Serpent Trail | Escape rooms: ordering and extraction | Unlock a hidden survey passage | None |

## Deduction and Ordering

### 1. The Four Watchers

**Setup:** A treasure chest has four numbered sockets and four loose stone
figures: a wolf, owl, stag, and serpent. Pulling its handle tests their order.

**Clues:** An inscription reads: "The owl watches immediately before the stag.
The wolf stands at an end. The serpent stands after the stag, but never beside
the wolf." An arrow labels the sockets from first to fourth.

**Solution:** Place the figures **wolf, owl, stag, serpent**. The owl-stag pair
cannot occupy the last two sockets because the serpent must follow; putting
the wolf last would force the serpent beside it.

**Failure and hints:** A wrong arrangement produces a loud growl and releases
the figures without harming anyone. If the group stalls, a worn relief shows
the owl and stag sharing a pedestal.

**Reward:** The chest opens to reveal a valuable moonstone and a signet ring
that identifies a forgotten noble family.

### 2. The Honest Guardian

**Setup:** Three doors bear a crown, a flame, and a wave. Above them is the
promise: "Exactly one inscription speaks truth. Exactly one door leads onward."
A central dial selects a door, and a lever tests the choice.

**Clues:** The crown door says, "The way onward is behind this door." The flame
door says, "The way onward is not behind this door." The wave door says,
"The way onward is not behind the crown."

**Solution:** Select **the flame**. If the crown were correct, the first two
statements would be true; if the wave were correct, the last two would be true.
Only the flame makes exactly one statement true: the wave's inscription.

**Failure and hints:** Wrong selections briefly open shallow alcoves whose
brass faces shout an alarm, then reset the dial. Chalk and a slate nearby allow
players to test each possibility explicitly.

**Reward:** The flame door opens a shortcut around a guarded hall; an alcove
beyond contains a safe resting niche.

## Light and Spatial Manipulation

### 3. The Borrowed Sunrise

**Setup:** A chamber contains a magical lamp, an empty lens holder, two
pivoting mirrors, and a sun-shaped receiver above a sealed stairway. Channels
in the floor trace a route from lamp to first mirror, then second mirror,
then receiver.

**Clues:** A mural shows a glass sun held before a lantern, with its light
passing through two silver hands to wake a sleeping gate. An adjacent plaque
reads, "The astronomer keeps the dawn."

**Required item:** The **sun lens** rests in an accessible astronomer's study
elsewhere on the current level, in a case marked with the same sun symbol.
Taking it requires no puzzle-dependent key.

**Solution:** Fit the lens into the lamp holder, then rotate both mirrors to
follow the marked route. The lens focuses the otherwise diffuse glow into a
visible beam; the correctly aligned beam activates the receiver.

**Failure and hints:** Incorrect angles simply leave the receiver dark.
Dust in the room makes the beam easy to follow, and scrape marks indicate
each mirror's useful range. A missing or broken lens can be repaired or
replaced by the dungeon's glassworker in exchange for a favor.

**Reward:** The stairway opens to the next level, and the lens remains removable
once the door latches open.

### 4. The Broken King's Shadow

**Setup:** Three carved panels slide sideways on separate tracks between a
fixed lamp and a wall. Their overlapping shadows can form a crowned king
holding a key. Each track has three numbered stops, and a handle tests the
arrangement.

**Clues:** An intact mosaic shows the target silhouette. A small maintenance
carving gives an additional clue: "Crown at two; hand at one; throne at three."
The corresponding panels carry crown, hand, and throne labels.

**Solution:** Move the **crown panel to stop 2, hand panel to stop 1, and throne
panel to stop 3**, then pull the handle. Describe the shadows joining into the
mosaic's image; no physical drawing or precise real-world lighting is needed.

**Failure and hints:** Wrong settings cast a visibly broken figure and do not
activate the latch. The maintenance carving can be found by inspecting the
lamp base without a required roll.

**Reward:** A hidden treasury opens, containing a jeweled ceremonial key and
a map marking one unexplored dungeon chamber.

## Sound and Sequence

### 5. The Silent Bell Choir

**Setup:** Once the party enters a choir room, its doors close. Four bells
bear a bird, sun, cup, and moon, but they have no clappers. A reset lever clears
any sequence already played.

**Clues:** A verse reads: "The bird wakes us; the sun guides our labor; the cup
ends our toil; the moon guards our rest." A carving shows a robed attendant
striking the bells with a bronze rod.

**Required item:** The **bronze striker** hangs in an open attendant's cupboard
in the corridor before the room, beside a sketch of the four bells.

**Solution:** Strike **bird, sun, cup, moon** in that order. Only the enchanted
striker registers, but it need not be wielded by a particular character.

**Failure and hints:** A wrong note clears the sequence and animates a scolding
stone choir. There is no countdown or suffocation hazard. If the striker was
missed, an interior emergency crank slowly opens the entrance door; using it
also rings an alarm elsewhere in the dungeon.

**Reward:** Both doors open, and a compartment offers a silver tuning fork
valuable to musicians or useful as a later magical focus.

### 6. The Ferryman's Footsteps

**Setup:** A flooded shaft has four rune-marked stepping stones: reed, fish,
boat, and shore. Each correct step raises the next stone; all four can be
reached from the starting ledge while the puzzle is inactive.

**Clues:** Pulling a chain plays four distinct sounds: wind through reeds,
a splash, creaking oars, and a harbor bell. A relief pairs each sound with
its rune, including a bell mounted on a shore-side dock.

**Solution:** Touch or step on **reed, fish, boat, shore** in order. A character
can test the stones with a pole from the ledge before anyone commits to crossing.

**Failure and hints:** A wrong selection returns the stones slowly to their
starting height, with enough warning to retreat; it never drops a character
without warning. The chain repeats the sequence as often as needed, and its
mechanism also displays the four matching pictures in order for groups that
prefer a visual clue.

**Reward:** The stones lock into a permanent bridge to the far landing, where
an abandoned ferryman's box holds coins and a waterproof route chart.

## Measurement and Resource Manipulation

### 7. The Apothecary's Balance

**Setup:** Eight identical sealed medicine tins stand beside a two-pan balance
and a locked reliquary. Exactly one tin is heavier; placing it in a separate
recess opens the lock. The balance permits only two weighings before a manual
reset.

**Clues:** The apothecary's note states: "Seven weigh alike. The eighth bears
my gold. Two questions to the scales will find it." The tins can be marked
or numbered freely.

**Solution:** Weigh **three tins against three**. If they balance, compare the
two unweighed tins; the heavier is the answer. Otherwise, take the three from
the heavier pan and weigh one against another: the heavier one is correct,
or the third is correct if those two balance.

**Failure and hints:** A wrong tin locks the recess for one minute before
ejecting it. Resetting the balance requires turning a noisy wheel, not an
expendable resource. A diagram under the balance depicts groups of three,
three, and two.

**Reward:** The reliquary contains a restorative potion and the apothecary's
gold reserve. Breaking tins open also exposes the gold, allowing a destructive
shortcut, but ruins their collectible medicinal seals.

### 8. The Thirsty Door

**Setup:** A cistern blocks a descending passage. Beside it are an unlimited
water spout, a drain, unmarked three-liter and five-liter jugs, and a receiving
bowl. The bowl's lever tests its contents and drains it after a wrong attempt.

**Clues:** Jug capacities are engraved on their handles. The door reads:
"Give me exactly four measures, neither less nor more." A pictogram defines
one measure as one liter and shows filling a jug, emptying it, and pouring
between jugs.

**Solution:** Fill the five-liter jug and pour into the three-liter jug,
leaving two liters. Empty the three-liter jug and transfer those two liters
into it. Refill the five-liter jug, then top up the three-liter jug with one
liter. **Four liters remain in the five-liter jug**; pour these into the
receiving bowl and pull the lever.

**Failure and hints:** Wrong amounts drain harmlessly away with a message of
"too much" or "too little." The water supply never runs out. A scratched note
says, "First keep two in the smaller vessel."

**Reward:** The cistern drains, exposing stairs to a lower level and a small
offering of old silver coins on the lowest step.

## Item Matching and Exploration

### 9. The Pilgrim's Three Offerings

**Setup:** A vault door has three identical recesses beneath images of an
empty granary, a battlefield survivor, and a traveler at a dark crossroads.
An inscription asks: "Feed the hungry, mend the wounded, guide the lost."

**Required items:** Three durable tokens can be collected in any order from
accessible side chambers: an **ear of wheat** from the abandoned kitchen,
a **bandaged hand** from the infirmary, and a **lantern** from the gatehouse.
Each location contains a mural connecting its token to the corresponding act
of mercy, and none lies beyond the vault.

**Solution:** Place **wheat beneath the granary, the bandaged hand beneath the
survivor, and the lantern beneath the crossroads**. All tokens fit all sockets,
so meaning rather than shape determines the answer.

**Failure and hints:** Wrong placements gently eject all tokens. If an original
token is lost, the door accepts a recognizable carved or drawn substitute;
an inscription inside a recess explains, "The deed's sign, not its substance."

**Reward:** The vault contains a valuable pilgrim's necklace and supplies,
and opens a sheltered route past a dangerous dungeon faction.

### 10. The Absent Jailer

**Setup:** A prison chamber seals when someone opens its evidence cabinet.
Inside are three labeled hooks: **PERSON**, **OFFICE**, and **POSSESSION**.
A portrait shows the jailer wearing a brass badge and carrying a key ring;
the cabinet contains a clay likeness of the jailer and that key ring.

**Clues:** The release mechanism reads: "Name the keeper, show their authority,
yield what they guard." Beneath the hooks is a second clue: "A face is not a
rank; a rank is not a key."

**Required item:** The **brass jailer's badge** lies on a desk in the guardroom
before the prison. A duty roster there identifies it as the badge of office,
not a personal ornament.

**Solution:** Hang the **clay likeness on PERSON, badge on OFFICE, and key ring
on POSSESSION**, then pull the release handle. Objects have loops or cords
so no improvised attachment is necessary.

**Failure and hints:** An incorrect arrangement sounds a single warning gong
but does not consume the objects. If the party missed the badge, a speaking
tube reaches a bored guard spirit, who lends a spare in exchange for a true
story about the world outside; the spirit can also clarify what "office"
means. The spirit always answers and does not require a successful roll.

**Reward:** The exit unlocks and the evidence cabinet's false back opens,
revealing confiscated jewelry and a letter exposing a dungeon resident's secret.

## Spirit Bargains and Identity

### 11. The Spirit Who Sold the Door

**Setup:** A merchant spirit guards a doorway and demands "a possession freely
given that leaves you no poorer." Coins and equipment offered as payment float
back into their owners' hands.

**Clues:** Ask about its old business and it admits it traded in stories.
Its ledger reads, "A tale told is a treasure shared, not a treasure lost."
It explains that it wants something new to it, not necessarily a secret.

**Solution:** Give the spirit **a story, joke, song, or piece of knowledge**
that it has not heard before. The party keeps its own knowledge while the
spirit gains something; an invented story explicitly counts.

**Failure and hints:** Unsuitable payments are returned with an explanation.
If players stall, the spirit asks what the surface sky looked like today.
Do not reject a reasonable contribution because it is short or ordinary.

**Reward:** The spirit opens the doorway and trades back a useful fact about
the next dungeon area.

### 12. The Name in the Well

**Setup:** A well spirit can raise a submerged bridge but has forgotten its
name. Three name slots circle the well, and speaking a proposed name causes
the water to repeat it.

**Clues:** A relief reads, "My beginning is dawn, my middle is water, my end
is home." A nearby glossary translates dawn as **EL**, water as **AN**, and
home as **OR**. The spirit remembers the meanings, but cannot read the relief
from inside the well.

**Required item:** An **inscribed name fragment** in an accessible flooded
caretaker's hut supplies the missing middle section of the relief and its
water symbol. A bucket and rope there allow retrieval without swimming.

**Solution:** Restore the fragment and speak **El-an-or**. Reasonable spelling
or pronunciation variations work; identifying and communicating the three
parts matters, not guessing the GM's preferred pronunciation.

**Failure and hints:** Wrong names cause harmless ripples. The spirit repeats
any correct beginning, helping the group locate a mistake. If the fragment
is destroyed, its impression survives in the hut's clay repair mold.

**Reward:** The bridge rises permanently, and the grateful spirit reveals a
hidden pearl before departing.

### 13. The Court of Three Ghosts

**Setup:** Three ghosts endlessly retry a theft, blocking a stairway until
someone identifies who took a sapphire. They agree that exactly one of them
did it and all three now tell the truth; their quarrel concerns timing.

**Clues:** The cook says, "It was still there when I left at the first bell."
The guard says, "I entered at the second bell, and its case was already empty."
The scribe says, "I alone was in the room between those bells." A visible
memory mural confirms that there was no other entrance, remote magic, or
accomplice. The scribe insists, "But I was only safeguarding it!"

**Solution:** Explain that **the scribe removed the sapphire between the first
and second bells**, whether or not the intention was theft. Ask where it was
put; the scribe then remembers the hollow foot of the writing desk.

**Failure and hints:** Accusations without a timeline restart the argument,
not combat. The ghosts answer specific questions consistently and can replay
their arrivals and departures as silent images.

**Reward:** Returning the sapphire to its display ends the trial and clears
the stairs; the ghosts award a separate silver advocate's chain.

### 14. A Lantern for the Forgotten

**Setup:** A keeper spirit tends four memorial lanterns marked crown, hammer,
needle, and bowl. All are dark. A chest beneath them reads, "Remember the deed,
not the station."

**Clues:** Ask whom the lanterns commemorate and the keeper describes a ruler
who fed refugees, a smith who repaired a floodgate, a tailor who stitched
bandages, and a beggar who warned the city. Four reusable flame tokens are
labeled **shelter**, **repair**, **healing**, and **warning**.

**Solution:** Give **shelter to the crown, repair to the hammer, healing to the
needle, and warning to the bowl**, explaining the remembered deeds. The keeper
accepts a brief summary rather than exact wording.

**Failure and hints:** A mismatched lantern projects the relevant memory and
returns its token. The keeper challenges assumptions such as equating a crown
with glory, but never conceals the necessary stories.

**Reward:** The chest opens to offer four modest gems and a lantern that glows
softly whenever its bearer speaks one of the remembered names.

## Construct Logic and Commands

### 15. The Golem's Literal Orders

**Setup:** A golem stands on a hatch. Its orders read: "Remain on a blue square.
Move only to an adjacent blue square. Never cross bare stone." Beside it are
three loose floor tiles, each red on one face and blue on the other.

**Clues:** The golem willingly recites its orders and explains that movable
tiles qualify as squares. An adjacent alcove is three tile-widths from its
current square; the hatch opens once its weight leaves the lid.

**Solution:** Lay the tiles **blue-side up in a continuous path** to the alcove,
then ask the golem to walk along them. It can follow any polite instruction
that does not conflict with its posted rules.

**Failure and hints:** Illegal commands produce a precise explanation rather
than hostility. The golem can lift a tile to demonstrate its other face but
cannot lay its own route, because its hands cannot reach outside its square.

**Reward:** The hatch opens to a lower level, and the golem offers to hold it
while the party descends.

### 16. The Statues That Would Not Bow

**Setup:** Three knight statues stand around an empty throne. Pressing one
statue's pedestal toggles its posture and that of its immediate neighbor to
the right; the last pedestal affects only its own statue. All begin standing.

**Clues:** Each pedestal has a clear diagram showing which statues it affects.
The door reads, "Let every knight kneel before the absent sovereign." A reset
cord returns all three to standing.

**Solution:** Press **the leftmost pedestal, then the rightmost**. The first
press kneels the left and middle knights; the second kneels the right knight.
Either order works.

**Failure and hints:** Other sequences merely change the displayed postures.
The knights complain theatrically but explain which linkage moved them.
If needed, point out that only the leftmost button affects the leftmost knight.

**Reward:** The royal tomb opens, and the statues salute the party as temporary
honor guards.

### 17. The Porter with Two Burdens

**Setup:** A stone porter operates a lift only while its two suspended baskets
weigh the same. The left basket contains a fixed four-unit counterweight and
the right a fixed ten-unit counterweight. Three loose blocks weigh one, two,
and three units, and all must be loaded.

**Clues:** Every weight is labeled, and the porter says, "What I already carry
counts too." The counterweights cannot be removed, but a release lever clears
all loose blocks for another attempt.

**Solution:** Put **all three blocks in the left basket**: four plus one plus
two plus three equals ten. The puzzle tests the assumption that loose weights
must be distributed between both sides.

**Failure and hints:** An unequal load tilts a pointer toward the heavier
side without moving the lift. The porter asks the group to count the weight
already in each basket.

**Reward:** The balanced mechanism locks safely and raises the party to a
treasure balcony; the lift remains usable afterward.

### 18. The Gardener of Stone

**Setup:** A gardener golem can grow a stone bridge from three enchanted pots,
but its instruction strip has fallen apart. Four command plaques read
**PLANT**, **WATER**, **SING**, and **HARVEST**.

**Clues:** The golem says water must follow planting, singing must occur
immediately before watering, and harvesting comes last. Diagrams define
harvesting as extending the grown stone vine across the chasm.

**Solution:** Arrange **PLANT, SING, WATER, HARVEST** and pull the start lever.
The golem supplies the seed, song, and water itself.

**Failure and hints:** Before executing a wrong sequence, the golem identifies
the first broken rule and returns the plaques. Its practice pot demonstrates
each command without consuming materials.

**Reward:** A permanent stone-vine bridge grows across the chasm, bearing one
gem-like fruit valuable to an artisan.

## Monster Negotiation and Perspective

### 19. The Troll's Fair Toll

**Setup:** A surprisingly scrupulous troll has sworn to collect "one gold coin
from every traveler who crosses my bridge." It refuses cheaper payment but
admits its contract says nothing about keeping the coins.

**Clues:** The full contract hangs on a post and also requires the troll to
pay one gold coin for each inspection of its bridge's underside. It complains
that nobody ever reads the maintenance clause. A safe stair reaches the
underside from either bank.

**Solution:** Use **one coin repeatedly**: pay for one traveler, have that
traveler inspect the underside and report a condition, then collect the
inspection fee and hand the coin back for the next traveler. Each traveler
may claim one inspection payment, even for confirming sound masonry.

**Failure and hints:** The troll refuses incomplete reports but offers an
example: "Third arch has moss." If the group has no gold, one traveler can
inspect from the near bank first to earn the initial coin.

**Reward:** Everyone crosses without a net loss of money, and the pleased
troll shares the location of a nearby weak wall.

### 20. The Ogre's Supper Guests

**Setup:** An ogre has stolen a dungeon key and offers to return it if the
party seats three touchy guests correctly. Chairs run left to right as viewed
from the entrance. The guests are a goblin drummer, a skeleton, and a kobold cook.

**Clues:** Speak to each guest: the drummer refuses to sit beside the cook;
the skeleton insists on the middle chair; the cook wants the chair nearest
the oven, which is on the right. The ogre agrees to these rules in advance.

**Solution:** Seat **the drummer on the left, skeleton in the middle, and cook
on the right**. The skeleton buffers the quarrelsome living guests.

**Failure and hints:** An unhappy guest explains the violated preference and
stands up. The ogre grows impatient but accepts retries; a snack from its
well-stocked pantry restores its good humor.

**Reward:** The ogre returns the key and provides a meal and gossip about the
other dungeon inhabitants.

### 21. The Wizard Who Could Not Give

**Setup:** A wizard wants the party to have a magical key, but a curse prevents
giving, lending, abandoning, or allowing theft of any possession. The wizard
can make fair exchanges and explains these limits openly.

**Clues:** A brass appraisal scale assigns the key three trade marks. Nearby
placards price a blank scroll at one mark, a bottle of ordinary ink at two,
and a brass candlestick at four. The wizard's trade rules forbid change.
The scroll and ink are in an unlocked visitors' supply cupboard and explicitly
belong to whoever takes them; the candlestick belongs to the wizard.

**Solution:** Offer **the scroll and ink together** as an exact three-mark
exchange for the key. Other party-owned goods work if the appraisal scale
values them at exactly three marks.

**Failure and hints:** The scale states each offered total before any exchange
occurs. The wizard rejects property already belonging to the wizard and asks,
"What two things together equal three?"

**Reward:** The party obtains the key, and the wizard gains useful supplies
without violating the curse.

### 22. The Cleric's Last Blessing

**Setup:** An elderly cleric guards a sanctuary but has only one blessing
left. A mural depicts three needy figures: a thirsty traveler, a wounded
soldier, and a frostbitten child. A basin offers water, clean bandages, and
a warm cloak; the cleric asks the party to reserve the miracle for whoever
cannot be helped with ordinary means.

**Clues:** Examining the living mural reveals that the traveler has a sound
cup, the soldier's wound bleeds endlessly through any dressing, and the child
is cold but otherwise healthy. The cleric confirms these observations without
requiring medical knowledge.

**Solution:** Offer **water to the traveler, the cloak to the child, and request
the blessing for the soldier's cursed wound**. Bandages can comfort the soldier
but cannot cure the visible curse.

**Failure and hints:** The cleric discusses a proposed blessing before using
it, so a mistaken suggestion cannot consume the only solution. Mural figures
describe whether an offered aid addresses their need.

**Reward:** The sanctuary opens as a safe resting place, and the cleric gives
the party an ivory holy symbol from a donation chest.

## Time and Coordinated Action

### 23. The Clockmaker's Borrowed Minute

**Setup:** A clockwork spirit traps the party in a room that repeats a short
cycle. At the cycle's end, loose objects and mechanisms return to their initial
states; characters retain their positions, memories, and carried belongings.
Three wall levers are labeled **REMEMBER**, **WIND**, and **OPEN**.

**Clues:** A plaque reads, "Remember before winding; open after the hour has
returned." The spirit explains that REMEMBER preserves the next mechanism
operated through exactly one reset. WIND charges the door spring, but OPEN
responds only in the cycle after charging.

**Solution:** Pull **REMEMBER, then WIND**, allow one reset, then pull **OPEN**.
The preserved spring charge survives into the cycle when the door can use it.

**Failure and hints:** Without REMEMBER, the spring visibly unwinds at reset.
Trying OPEN too early produces "Come back next cycle." Handle cycles as player
declared actions, not a real-world timer; the spirit explains any lost charge.

**Reward:** The party escapes with a silver pocket watch, and the spirit is
released from maintaining the loop.

### 24. The Duet with Yesterday

**Setup:** A door requires two floor plates to be held while a lever is pulled.
A musician's ghost offers one magical echo that can replay up to three actions
by one character. The recording pedestal stands beside the lever; the two
plates are several paces apart.

**Clues:** The ghost demonstrates that an echo can move, stand on a plate, and
remain there until dismissed. It has weight but cannot leave the room. A
recording slate displays the actions before playback.

**Solution:** Record **walking to the first plate and waiting**, then end the
recording verbally. Replay it while a character holds the second plate and
another pulls the lever. A lone adventurer can use the provided stone bench
to weight the second plate; moving it takes effort but no special ability.

**Failure and hints:** Bad recordings can be erased freely. The ghost suggests
recording a sustained action rather than rushing between all three stations.
The door latches open once triggered, so nobody must be left behind.

**Reward:** The sound-sealed door opens into a musician's treasury containing
a fine instrument and silver strings.

### 25. The Guardian Who Walked Backward

**Setup:** A spectral sentinel patrols four numbered floor bands in a gallery.
Its repeating positions are **1, 2, 3, 4, 3, 2**, one position per bell beat.
A control alcove offers a one-use-per-cycle PAUSE lever and a CROSS lever.

**Clues:** A diagram shows that CROSS sends a warded platform through bands
1, 2, 3, and 4 over four beats. The platform and sentinel may not occupy the
same band on the same beat, but can pass between bands safely. PAUSE delays
the platform's departure by one beat; it does not stop the sentinel.

**Solution:** Trigger CROSS **on the beat when the sentinel is at band 2 moving
toward band 3**. The platform then occupies 1, 2, 3, 4 while the sentinel
occupies 2, 3, 4, 3. No positions coincide. The lever's posted rule says the
first platform move occurs on the triggering beat.

**Failure and hints:** A miniature preview shows all four beats before
departure and rejects collisions without exposing riders. The sentinel
answers questions about its route; PAUSE can correct a departure selected
one beat too early but is not required.

**Reward:** The platform delivers everyone across the warded gallery and
unlocks a safe return walkway.

### 26. The Four Seasons' Audience

**Setup:** An enchanted tree statue changes through spring, summer, autumn,
and winter whenever a wheel turns. Four petitions must be delivered in their
appropriate seasons before the statue will reveal a staircase.

**Clues:** Petitioners' carved voices ask to **sow**, **ripen**, **gather**, and
**rest**. A mural links sowing to spring blossoms, ripening to summer sun,
gathering to autumn leaves, and rest to winter snow. The statue explains that
the cycle must begin with sowing and proceed without skipping a season.

**Solution:** Turn to **spring and present sowing**, then advance through
**summer/ripening, autumn/gathering, winter/rest**. The petition plaques are
all supplied at the statue's base.

**Failure and hints:** A mismatched petition is returned with a seasonal clue;
it does not erase prior correct petitions. Skipping a season resets the
sequence, but the wheel can always be turned around to start again.

**Reward:** Roots withdraw from a descending staircase and expose a small
amber bird that can carry one short spoken message to a nearby room.

## Ritual Repair and Exploration

### 27. The Golem's Missing Heart

**Setup:** A disabled lift golem has three empty heart sockets marked with
an ear, a flame, and a hand. Its head still speaks, asking to "hear the need,
find the will, then do the work."

**Required items:** A **silver chime** lies in an accessible bell workshop,
a **warm coal crystal** in a cold forge, and a **copper gear** in a storeroom.
Signs from the lift point toward all three rooms, and none requires the lift
to reach it. Each component is safe to carry.

**Clues:** Workshop diagrams associate the chime with listening, the crystal
with power, and the gear with movement. The golem can describe those functions
but cannot see inside its own chest.

**Solution:** Fit **chime to ear, crystal to flame, gear to hand**, then activate
them in that order by pressing their sockets. The golem confirms each stage:
"I hear"; "I will"; "I act."

**Failure and hints:** Wrong parts are ejected intact, and an incorrect
activation sequence powers down safely. Replacement parts can be assembled
from clearly labeled spares in their respective rooms if originals are lost.

**Reward:** The lift resumes service, and the golem becomes a helpful guide
to the level, though its body remains attached to the lift mechanism.

### 28. The Feast for an Empty Mouth

**Setup:** A kitchen spirit guards a treasure cache but cannot eat material
food. It begs for the feast it remembers: "Not the bread, but its welcome;
not the broth, but its breath; not the cup, but its celebration."

**Required item:** A **recipe tablet** in the accessible dining hall describes
the old welcome ritual and depicts a hearth, a steaming covered pot, and
raised empty cups. The kitchen has replenishing illusory provisions.

**Clues:** Conversation reveals that the spirit experiences **aroma, steam,
and spoken toasts**, but not solid food or drink. It remembers that guests
were welcomed first, warmed second, and honored last.

**Solution:** **Warm the supplied bread to release its aroma, uncover the
steaming broth, then raise a cup and offer a toast**, in that order. Equivalent
aromas and warm dishes work; the toast may be one simple sentence.

**Failure and hints:** Material offerings pass harmlessly through the spirit,
which explains what it could sense. The recipe has a duplicate painted on
the dining-hall wall if the tablet is missed or damaged.

**Reward:** The satisfied spirit opens its cache of silver tableware and
teaches the party the location of a concealed servants' passage.

### 29. The Rust Keeper's Hunger

**Setup:** A tame rust monster sleeps behind a crystal partition beside an
iron grate blocking a passage. Its goblin keeper wants the grate removed but
must prevent the creature from eating a bronze warning bell beside it.

**Clues:** The keeper explains that the creature eats exposed metal of either
kind and follows the nearest visible metal. Opaque leather covers conceal
metal completely from its senses. The room contains a fitted bell cover,
a wooden target pole, and reusable metal lure rings; a safe demonstration
behind the partition confirms these rules.

**Solution:** **Cover the bell, put away or cover carried metal, and use a ring
on the wooden pole to lead the creature to the grate**. Withdraw the lure
through the partition's small feeding slot so the grate becomes its nearest
reachable meal. The keeper then releases it.

**Failure and hints:** The keeper checks the setup before opening the partition,
pointing out exposed valuables or the uncovered bell. The creature is trained
to return when a wooden rattle sounds, providing a safe abort without combat.

**Reward:** The grate is eaten, the bell remains functional, and the keeper
offers a vial of rust-resistant equipment oil.

### 30. The Saint Whose Shadow Lied

**Setup:** An enchanted saint's statue maintains a ward across stairs to the
lowest level. Its voice commands obedience, but its shadow silently acts out
mercy: lowering a sword, opening a cage, and sharing bread. A resident cleric
suspects the statue's spoken liturgy has been altered.

**Required item:** The **true oath tablet** rests in an accessible novice's
schoolroom. It reads, "Disarm wrath; release the captive; feed the stranger."
A rubbing in the schoolroom serves if the tablet cannot be moved.

**Clues:** The cleric explains that the statue reenacts whichever oath is
placed on its lectern. Its current tablet instead praises punishment,
imprisonment, and hoarding. Nearby are a hinged wooden sword, a cage holding
an illusory bird, and a basket of bread beside a beggar-shaped bowl.

**Solution:** Replace the false tablet with **the true oath or its rubbing**,
then **fold the sword down, open the cage, and put bread in the beggar's bowl**.
These acts fulfill the three clauses in order; the cleric can read them aloud
for characters who cannot read the script.

**Failure and hints:** Wrong actions make the shadow repeat the relevant
merciful gesture. The cleric can reset all props, and the statue's threats
remain theatrical rather than imposing an unannounced combat encounter.

**Reward:** The restored statue removes the ward, grants access to the lower
level, and opens a donation drawer containing a valuable sun-shaped brooch.

## Strategy Games: Nim

These are **normal-play Nim**, not misere Nim: taking the last object wins.
The players always move first, and every listed initial nim-sum is nonzero.
Each game is deterministic; random dungeon selection does not introduce luck
into playing the game. A loss restores the identical starting position and
permits unlimited free retries, not a new randomized or potentially unwinnable
position. The enchanted playing pieces cannot be kept as treasure.

### 31. The Troll's Three Gem Heaps

**Game:** Normal-play Nim
**Dungeon levels:** 1+
**Starting piles:** 3, 4, 5
**Winning opening:** 1 -> 1

**Setup:** A troll accountant sits before three numbered bowls of enchanted
gems: three rubies, four sapphires, and five emeralds. Its real treasure chest
opens only when someone beats its counting game.

**Rules:** The party moves first; on each turn remove one or more gems from
exactly one bowl. The troll then takes a turn under the same rule. Taking the
last gem wins. Passing, transferring gems, and emptying multiple bowls in one
turn are illegal and politely refused.

**Clues:** A slate writes each heap in binary: `011`, `100`, `101`.
The troll explains how to count odd and even columns, but will not volunteer
which heap to reduce.

**Solution:** The initial xor is **2**, not zero. Remove two rubies, leaving
**1, 4, 5**, whose xor is zero. After every troll move, compute the xor `s`
of the remaining heaps and reduce a heap `h` to `h xor s` whenever that is
smaller than `h`. Such a reduction always exists from a nonzero-xor position.
Return xor zero after every player turn; the party must eventually take the
last gem.

**Guardian policy:** With nonzero xor, the troll makes the xor-zero reduction
in the lowest-numbered eligible bowl. With zero xor, it removes one gem from
the lowest-numbered nonempty bowl. These tie-breaks are fixed, not rolled.

**Failure and hints:** If the troll takes the last gem, all bowls immediately
reset to 3, 4, 5. The players may retry without limit or cost and always go
first. The troll will demonstrate xor column addition after a loss.

**Reward:** On victory, all playing gems vanish and the separate chest opens
to reveal a real cut ruby and a silver counting frame.

### 32. The Fourfold Coin Tithe

**Game:** Normal-play Nim
**Dungeon levels:** 1+
**Starting piles:** 2, 3, 5, 7
**Winning opening:** 1 -> 1

**Setup:** A cleric's animated statue presents four numbered stacks of glowing
coins. It calls the game a lesson in leaving every account balanced.

**Rules:** Players first, then statue, alternating; remove any positive number
of coins from one stack only. The player taking the final coin wins.
There is no passing or mixing stacks, and the coins cannot leave the altar.

**Clues:** Above each stack, a light displays its count in binary. A plaque
reads, "Balance the parity of every column, not the total wealth."

**Solution:** The xor of **2, 3, 5, 7 is 3**. Take one coin from stack 1,
leaving **1, 3, 5, 7**, whose xor is zero. After every reply, reduce one
stack from `h` to `h xor s`, where `s` is the new xor, choosing a stack for
which that value is smaller. Equal total sums are irrelevant.

**Guardian policy:** The statue takes a xor-zero move in the first eligible
stack when possible; otherwise it removes one coin from the first nonempty
stack. Its choices never depend on dice.

**Failure and hints:** A statue victory restores exactly 2, 3, 5, 7.
Retries are unlimited, free, and always player-first. An incorrect or illegal
move does not consume money from the characters' own purses.

**Reward:** On victory, the playing coins disappear and an offering coffer
opens, containing ordinary silver coins and a finely worked ceremonial bowl.

### 33. The Three-Rail Stone Race

**Game:** Normal-play Nim
**Dungeon levels:** 1+
**Starting piles:** 2, 5, 8
**Winning opening:** 3 -> 7

**Setup:** A bridge golem controls a **3-by-9 board**: three separate tracks,
each with squares numbered **0 through 8** from left to right. One marker
starts on square 2 of track 1, square 5 of track 2, and square 8 of track 3.
The square number, not the number of empty squares including zero, is its heap.

**Rules:** The party moves first. On a turn, slide one marker any positive
distance left along its own track, never past square 0. Markers cannot move
right or change tracks. Whoever makes the move that parks the final marker
at zero wins; a marker already at zero cannot move.

**Clues:** Three counters repeat the markers' distances from zero. The golem
can demonstrate that moving a marker three squares is the same as removing
three stones from a pile.

**Solution:** The starting distances **2, 5, 8 have xor 15**. Slide marker 3
from 8 to **7**, leaving **2, 5, 7** with xor zero. After every golem move,
slide one marker from `h` to `h xor s < h`, where `s` is the current xor.
This is ordinary Nim in a different physical form.

**Guardian policy:** The golem chooses the first track with a xor-zero move;
if none exists, it moves the first nonzero marker left by one square.

**Failure and hints:** If the golem parks the last marker, all markers return
to 2, 5, 8. Unlimited free retries always give the players the first turn.
The bridge remains retracted until a win; no one falls during a failed game.

**Reward:** All markers sink into their zero squares and the passage bridge
lowers and locks in place.

### 34. The Four Sentinels' Retreat

**Game:** Normal-play Nim
**Dungeon levels:** 1+
**Starting piles:** 1, 4, 6, 8
**Winning opening:** 4 -> 3

**Setup:** Four miniature stone sentinels occupy a **4-by-9 board**, one per
track. Tracks have exactly nine squares labeled **0 through 8**. The
sentinels begin at distances 1, 4, 6, and 8 from their home squares.

**Rules:** Players act first. Each turn retreats one sentinel any positive
number of squares toward zero. No advancing, changing tracks, or passing is
allowed. Whoever sends the final sentinel home wins.

**Clues:** A spectral captain calls this "the same war with four armies."
Its banner displays the counts `0001`, `0100`, `0110`, and `1000`, and explains
that a winning commander leaves an even number of lights in each binary column.

**Solution:** The xor is **11**. Retreat sentinel 4 from 8 to **3**,
leaving **1, 4, 6, 3**, whose xor is zero. Continue restoring xor zero after
each captain's move, using `h -> h xor s` for a track where the value decreases.

**Guardian policy:** The captain uses the first available xor-zero reduction,
or retreats the first nonzero sentinel one square when no such reduction exists.

**Failure and hints:** A loss returns the sentinels to 1, 4, 6, 8 and resets
all lights. Retries are unlimited and free, with the players first every time.
The captain will show why simply copying the previous move is not a general
solution for unequal heaps.

**Reward:** Victory makes the sentinels bow and unseals the onward gate.

## Strategy Games: Chess

A move budget counts **White's moves only**, not both sides' plies and not
elapsed seconds. The visible display decrements after each legal White move;
checkmate on the final allowed move succeeds before any reset. Earlier mates
also succeed. The party is always White and always moves first. Illegal moves
are refused without using a turn; stalemate, a drawn game, losing, or exhausting
the budget without mate resets the identical position for an unlimited free
retry. Any legal winning continuation counts, not just the printed solution.

The positions below come from publicly documented nineteenth-century games,
not copied modern-book annotations. The supplied trees cover **every legal
Black reply along the chosen White strategy**, including defenses absent from
the famous main line. For off-line play the TM can use a chess engine or play
the strongest defense available; no defense is chosen by rolling dice.
In diagrams, uppercase pieces are White, lowercase are Black, `.` is empty;
files run a-h from left to right and ranks 8-1 from top to bottom.

### 35. The Immortal's Last Three Turns

**Game:** Chess
**Dungeon levels:** 1-3
**Move budget:** 3
**FEN:** r1b1k1nr/p2p1ppp/n2B4/1p1NPN1P/6P1/3P1Q2/P1P1K3/q5b1 w kq - 2 21

**Setup:** A normal-sized ivory chessboard stands before a master's reliquary.
A ghostly tutor invites the party to finish the commonly published mating
continuation of **Anderssen-Kieseritzky, the Immortal Game (1851)**, after
20...Na6. The continuation is traditionally associated with the game, although
historical reports differ on when play actually ended. Three bright beads
above the board show how many White moves remain.

**Board:**
```text
r.b.k.nr
p..p.ppp
n..B....
.p.NPN.P
......P.
...P.Q..
P.P.K...
q.....b.
```

Read files a-h left to right and ranks 8-1 top to bottom; capitals are White,
lowercase letters are Black, and dots are empty squares.

**Rules:** Standard chess; White moves first and must checkmate within **three
White moves**. Black's turns do not consume beads, and this is not a real-time
clock. Black retains kingside and queenside castling rights as encoded in the
FEN, although the forced checks prevent castling in the winning line.
The enchanted pieces, not the characters, perform captures.

**Clues:** The tutor says, "Your king needs no rescue; the queen can finish
her work by leaving the board." If needed, point to the knight on f5.

**Winning lines:**
```text
Nxg7+ Kd8 Qf6+ Ne7 Bxe7#
Nxg7+ Kd8 Qf6+ Nxf6 Be7#
```

**Solution:** Play **21.Nxg7+**; Black's only legal reply is **21...Kd8**.
Then play **22.Qf6+**. If Black interposes **22...Ne7**, play **23.Bxe7#**;
if Black captures with **22...Nxf6**, play **23.Be7#**. These are all legal
defenses to the selected checks. Mate is forced in three White moves and
cannot be forced in two from the starting position.

**Guardian policy:** Along this strategy, the tutor chooses the first listed
available defense, so its correct-play replies are deterministic. On deviations,
it tries to defeat the mate deadline rather than reproducing an illegal or
cooperative historical move; it never rolls for a reply.

**Failure and hints:** A loss, draw, or third White move without checkmate
restores the same board and all three beads. Retries are unlimited and free;
White always starts. Illegal moves are simply refused. Mate on or before the
third White move succeeds.

**Reward:** The reliquary opens to reveal a jeweled chess knight and the
master's annotated map of nearby chambers.

**Source:** [Immortal Game, published score and historical qualifications](https://en.wikipedia.org/wiki/Immortal_Game).

### 36. The Evergreen Spectral Court

**Game:** Chess
**Dungeon levels:** 4+
**Move budget:** 4
**FEN:** 1r2k1r1/pbppnp1p/1b3P2/8/Q7/B1PB1q2/P4PPP/3R2K1 w - - 0 21

**Setup:** An eight-by-eight floor board holds translucent, larger-than-human
pieces. A spectral king presents **Anderssen-Dufresne, the Evergreen Game
(1852)**, after **20...Nxe7**, the position followed by the famous announced
mate. Four rings of light above a monumental gate count the party's remaining
White moves. This longer challenge is reserved for Level 4 or deeper.

**Board:**
```text
.r..k.r.
pbppnp.p
.b...P..
........
Q.......
B.PB.q..
P....PPP
...R..K.
```

Read files a-h left to right and ranks 8-1 top to bottom; capitals are White,
lowercase letters are Black, and dots are empty squares.

**Rules:** Standard chess, White first, no castling rights or en-passant
capture. Checkmate must occur within **four White moves**; Black's moves and
deliberation time do not spend rings. Characters direct the spectral pieces
without replacing them or risking their own lives.

**Clues:** The king boasts that two checking pieces cannot both be captured.
The queen on a4 and bishop on d3 glow briefly when a player asks for guidance.

**Winning lines:**
```text
Qxd7+ Kxd7 Bf5+ Kc6 Bd7#
Qxd7+ Kxd7 Bf5+ Ke8 Bd7+ Kd8 Bxe7#
Qxd7+ Kxd7 Bf5+ Ke8 Bd7+ Kf8 Bxe7#
Qxd7+ Kf8 Bxe7#
```

**Solution:** Begin **21.Qxd7+**. Against **21...Kf8**, **22.Bxe7#** ends
the game immediately. Against **21...Kxd7**, play **22.Bf5+**, a double check.
If **22...Kc6**, answer **23.Bd7#**. If **22...Ke8**, play **23.Bd7+**,
then **24.Bxe7#** against either **23...Kd8** or **23...Kf8**.
The longest defense requires four White moves; no strategy forces mate in
three from the initial position.

**Guardian policy:** The king chooses a longest surviving listed defense:
Kxd7, then Ke8, then Kd8 when the stated branches apply. For off-line play
it seeks the strongest legal defense, with no random choice or forced
cooperation.

**Failure and hints:** A loss, draw, or fourth White move without mate resets
the exact position and all four rings. Retries are unlimited and free, always
with White first. Illegal moves do not consume rings; an earlier checkmate,
including the two-move Kf8 branch, is a full success.

**Reward:** All spectral pieces kneel and the monumental gate opens.

**Source:** [Evergreen Game, score and alternative mating defenses](https://en.wikipedia.org/wiki/Evergreen_Game).

## Strategy Games: Go

These are small **Capture Go ladder challenges**, not claims that a whole
19-by-19 territory-scoring game can be won in a few moves. The announced victory
condition is to capture the marked White chain within a Black-move budget.
The party plays Black first; a guardian plays White. Standard orthogonal
connections and liberties apply, captured groups are removed before checking
suicide, and positional superko forbids repeating a previous board after a
placement. Passing is legal; a Black pass spends a move. There is no komi,
territory scoring, or randomly selected move.

Boards are five by five: columns **A-E** left to right, rows **5-1** top to
bottom; `B` is Black, `W` is White, and `.` is empty. A numbered light counter
tracks Black's turns, not elapsed time. The solutions account for every legal
White defense: until the last extension, the listed extension is the only
reply that avoids immediate capture. At the edge, even that last extension
leaves just one liberty, and every White reply loses on the next Black turn.

### 37. The Spirit's Short Ladder

**Game:** Capture Go
**Dungeon levels:** 1-3
**Move budget:** 3
**Target:** C4
**Winning line:** C5 D4 E4 D5 E5

**Setup:** A water spirit lays out a small Go board on a pearl casket.
The White stone at **C4** bears a fish symbol; its entire connected chain
must be captured. Black starts at B4, C3, and D3. Three illuminated pearls
count the party's remaining Black moves.

**Board:**
```text
.....
.BW..
..BB.
.....
.....
```

**Rules:** The party moves Black first and must capture the marked White
chain within **three Black turns**, using ordinary Go liberties, capture,
no suicide, and positional superko. The spirit plays White between turns.
Passes are allowed, but a Black pass consumes a pearl. There is no territory
score; only capturing the marked chain wins. In the diagram, B/W mean
Black/White; columns A-E run left to right and rows 5-1 run top to bottom.

**Clues:** The spirit demonstrates a liberty with a bubble on each empty
orthogonally adjacent intersection. It asks, "Can you make the edge become
your final wall?"

**Solution:** Play **Black C5, White D4, Black E4, White D5, Black E5**.
E5 captures the marked chain. At either White turn, any legal move other
than the listed extension, including passing, leaves the marked group with
one liberty: fill that liberty and capture it immediately instead of blindly
continuing the long line. The budget is a maximum, so early captures count.

**Guardian policy:** The spirit always makes the listed saving extension
when it applies, including the doomed last extension at the board edge.
It chooses moves strategically rather than randomly.
The guarantee also holds if it chooses any other legal defense.

**Failure and hints:** A third Black turn without capture, or surrender,
restores the exact board, marked stone, and three pearls. Retries are unlimited,
free, and Black-first. Illegal moves are refused without spending a turn.

**Reward:** On capture, the playing stones dissolve into mist and the separate
pearl casket opens.

### 38. The Five-Step Dragon Ladder

**Game:** Capture Go
**Dungeon levels:** 4+
**Move budget:** 5
**Target:** B3
**Winning line:** B4 C3 D3 C4 C5 D4 E4 D5 E5

**Setup:** A dragon-shaped stone guardian projects a giant five-by-five Go
grid over a warded passage. Black stones begin at **A3, B2, and C2**;
one marked White stone begins at **B3**. Five scales of light count the party's
Black turns. The longer ladder appears only on Level 4 or deeper.

**Board:**
```text
.....
.....
BW...
.BB..
.....
```

**Rules:** Black, controlled by the party, plays first. Capture the marked
White chain within **five Black moves**, not five combined moves. Use ordinary
Go connections and liberties, removal of captured groups, no suicide, and
positional superko. Passing is legal and a Black pass spends one scale.
There is no territory-scoring phase. B/W mean Black/White; columns A-E
run left to right and rows 5-1 run top to bottom.

**Clues:** Empty liberties glow whenever a stone is placed. The guardian
explains atari, but the party must work out which alternating liberties herd
the marked chain toward the upper-right corner.

**Solution:** Follow **Black B4, White C3, Black D3, White C4, Black C5,
White D4, Black E4, White D5, Black E5**. The fifth Black move captures the
entire marked chain. Until the final extension, the listed White extension
is its only defense against immediate capture; the final D5 extension is
already doomed to capture at E5. If White plays elsewhere or passes,
immediately fill the marked chain's sole liberty and win within the budget.

**Guardian policy:** The dragon uses those saving extensions along the
solution, without dice. Every other legal White reply loses to an immediate
capture (earlier in the ladder, sooner than the main line), so success does
not depend on cooperation.

**Failure and hints:** Five Black turns without capture reset the identical
position and all five scales. Unlimited free retries always let Black start.
Illegal moves do not consume scales; players can request a demonstration
of liberty counting before trying again.

**Reward:** The dragon dissolves the passage ward and permits onward travel.

## Strategy Games: Other Impartial Games

### 39. The Twin Tribute of Wythoff

**Game:** Wythoff
**Dungeon levels:** 1+
**Starting piles:** 3, 6

**Setup:** A two-headed golem guards a stairway with two bowls containing
three jade counters and six obsidian counters. The heads alternate reciting
the two legal kinds of move.

**Rules:** The party goes first. On a turn, remove any positive number from
**one** bowl, or remove the **same positive number from both** bowls. Taking
the last counter or counters wins. No passing is allowed. This is Wythoff's
game, not ordinary Nim; plain xor is not the correct strategy.

**Clues:** A floor mosaic depicts the five balanced pairs reachable in this
small game: **(0,0), (1,2), (2,1), (3,5), (5,3)**. The heads admit that no
legal move connects one of these pairs directly to another.

**Solution:** Remove one obsidian counter to leave **(3,5)**. After every
guardian turn, return to a reachable pair in the mosaic, ending at (0,0).
The reachable balanced pairs are precisely the losing positions within the
3-by-6 rectangle (the symmetric (5,3) is shown for teaching but cannot be
reached from this starting order). Every legal move away from (3,5) or the smaller
balanced pairs permits a move back to one of them.

**Guardian policy:** When a balanced pair is reachable, choose the first
such pair in the displayed order; otherwise remove one counter from the first
nonempty bowl. No outcome or tie-break is random.

**Failure and hints:** A guardian victory restores exactly three jade and
six obsidian counters. Players may retry without limit or cost and always
move first. Counters taken during play are illusions, not loot.

**Reward:** The golem lifts the seal from the stairway.

### 40. The Ogre's Forbidden Sweet

**Game:** Chomp
**Dungeon levels:** 1+
**Starting rows:** 3, 3, 3

**Setup:** A friendly ogre offers a game on a three-by-three tablet of glowing
sugar-shaped tiles. Columns are A-C left to right and rows 1-3 bottom to top.
The lower-left tile, **A1**, bears a skull, but is theatrical: taking it loses
the game rather than poisoning a character.

**Rules:** The party moves first. Choose one remaining tile; that tile and
every remaining tile **above it and to its right**, including tiles in the
same row or column, vanish. Equivalently, remove every tile whose row and
column are both at least those of the chosen tile. Whoever takes A1 loses.
Passing is forbidden; tiles cannot be restored except by resetting.

**Clues:** The ogre scratches a diagonal from A1 to C3 and observes that the
two arms of a balanced letter L are excellent partners.

**Solution:** Choose **B2** first, leaving just A1, B1, C1, A2, and A3:
two equal arms joined at the forbidden tile. Thereafter mirror the ogre's
choice across the A1-C3 diagonal: answer **B1 with A2**, **C1 with A3**,
**A2 with B1**, or **A3 with C1**, as applicable to the remaining tiles.
Each safe ogre move shortens one arm; the mirror shortens the other equally.
Eventually only A1 remains for the ogre, which must take it and lose.

**Guardian policy:** The ogre chooses a move leaving the opponent a losing
position if one exists; otherwise it chooses the alphabetically first safe
coordinate. With only A1 left it takes that tile. Its choices involve no dice,
and the mirror strategy defeats every possible legal reply after B2.

**Failure and hints:** If a player takes A1, the skull laughs and the full
three-by-three tablet resets. Retries are unlimited, free, and player-first.
Illegal selections are refused. No actual food, treasure, or character health
is consumed by a failed attempt.

**Reward:** Victory opens the ogre's pantry chest, revealing preserved treats
and a silver dessert service separate from the enchanted playing tiles.

## Escape Rooms: Substitution and Reading Order

Puzzles 41-50 each contain **2-4 genuine hidden clues and 2-4 hidden decoys**.
The cipher key and instructions are visible room fixtures, not extra hidden
clues. Table classifications, explanations, and final codes are **TM-only**:
describe discovered objects, their markings, and their text, never announce
"genuine" or "decoy." Every decoy fails an observable selection rule printed
on the key; players need not read the TM's mind to reject it.

These are ordinary WIS clue searches, not class-restricted trap checks.
A basic roll is three independent integers from 0 through 11, summed without
symbol rerolls. Add the WIS modifier and applicable level/class bonuses,
and meet or exceed the listed DC. A roll searches one named hiding place;
each retry costs one exploration turn. Precisely inspecting the actual
compartment, lining, or underside reveals its clue without another roll.
Failed searches never destroy clues. No outside item, language proficiency,
or additional cipher knowledge is needed beyond the supplied key.

### 41. The Fallen Delver's Last Account

**Escape code:** 472

**Setup:** A slain adventurer lies beside a three-wheel strongbox in a looted
guardroom. The box has digits 0-9 on each wheel and a sun-shaped seal matching
the adventurer's old company badge.

**Cipher key:** The visible badge reads, "Trust the sun. Read HEAD, HEART,
HEEL." Its reverse supplies the lookup: `FLAME=4, WAVE=7, ROOT=2, SKULL=9,
BOLT=5`. Only fragments carrying the matching sun seal belong to this account.

**Search:** Roll basic + WIS modifier + applicable bonuses against each
listed DC; a miss costs an exploration turn and permits another attempt.
Directly inspecting the precise hiding place reveals its clue without a roll.

| Kind (TM only) | Hiding place and visible identifying marks | WIS DC | Found text | TM interpretation |
| --- | --- | --- | --- | --- |
| Genuine | Inside the helmet lining; sun seal and HEAD label | 17 | FLAME | First digit, 4 |
| Genuine | Folded into the breastplate padding; sun seal and HEART label | 20 | WAVE | Second digit, 7 |
| Genuine | Under the boot's removable heel; sun seal and HEEL label | 20 | ROOT | Third digit, 2 |
| Decoy | Under the corpse's belt pouch; a moon-stamped gaming chit | 17 | SKULL | Wrong company seal, despite a valid lookup symbol |
| Decoy | Behind a loose brick; a lightning-stamped scrap | 20 | BOLT | No sun seal |
| Decoy | Inside a broken cup; an unmarked scrap of numbers | 17 | 593 | No sun seal or body-order label |

**Solution:** Select the three sun-sealed fragments, put them in HEAD,
HEART, HEEL order, and translate FLAME, WAVE, ROOT to **472**. The moon and
lightning markings are observable evidence against the competing scraps.

**Failure and hints:** A wrong combination clicks and returns the wheels to
zero; retries are unlimited. If the party mixes in a gaming chit, point out
that its seal differs from the strongbox's sun. No clue is consumed.

**Reward:** The box holds a valuable garnet and the adventurer's salvage
notes, including a warning about a nearby dungeon hazard.

### 42. The Apprentice's Borrowed Alphabet

**Escape code:** OPEN

**Setup:** A wizard's abandoned apprentice study contains a four-letter
door lock, half-finished exercises, and a portrait of a stern tutor.
The tutor's crown emblem is repeated on the lock.

**Cipher key:** A permanent alphabet strip on the desk says, "Use the crowned
lesson, I before II. Move each written letter back three places; wrap A to Z."
It shows the complete correspondence, with encoded letters above decoded ones:

```text
ABCDEFGHIJKLMNOPQRSTUVWXYZ
XYZABCDEFGHIJKLMNOPQRSTUVW
```

**Search:** Roll basic + WIS modifier + applicable bonuses against the listed
DC for a named hiding place. A failed attempt costs an exploration turn;
retries are allowed, and exact hands-on inspection finds the clue without a roll.

| Kind (TM only) | Hiding place and visible identifying marks | WIS DC | Found text | TM interpretation |
| --- | --- | --- | --- | --- |
| Genuine | Behind the tutor's portrait backing; crown stamp and I | 20 | RS | Decodes to OP |
| Genuine | Beneath the writing desk's pen tray; crown stamp and II | 17 | HQ | Decodes to EN |
| Decoy | In the wastebasket beneath torn exercises; marked PRACTICE, no crown | 17 | GOLD | An unrelated letter exercise, not a password hint |
| Decoy | Inside an empty ink bottle; apprentice's spiral mark, no crown | 20 | ABCD | Uses the wrong identifying mark |

**Solution:** Join the crowned fragments in I-II order to obtain RSHQ,
then shift each letter backward by three: **OPEN**. Enter the decoded word,
not the cipher text, on the four letter wheels.

**Failure and hints:** Incorrect words extinguish the portrait's eyes for
one exploration turn but do not erase evidence or prevent later attempts.
The tutor's portrait can demonstrate R becoming O without revealing the rest.

**Reward:** The study passage unseals, revealing access to the next dungeon
section and a small cache of unused spell-writing supplies.

### 43. The Tomb Painter's Backward Farewell

**Escape code:** BONE

**Setup:** A tomb painter died beside a covered funerary coffer. Its four
letter wheels sit below a polished bronze mirror, while abandoned repair
notes and burial tallies litter the chamber.

**Cipher key:** The coffer reads, "Only the square mason's seal. Join I then
II, then read the whole line from right to left." An example displays
`TAC -> CAT`. This reverses letter order, not letter shapes; no actual mirror
writing or special prop is required to run the puzzle.

**Search:** Use basic + WIS modifier + applicable bonuses versus the listed
DC. Failure costs an exploration turn, with unlimited retries; specifically
opening or inspecting the named hiding place reveals the clue without a roll.

| Kind (TM only) | Hiding place and visible identifying marks | WIS DC | Found text | TM interpretation |
| --- | --- | --- | --- | --- |
| Genuine | Folded inside the painter's sleeve; square seal and I | 17 | EN | First half of the written line |
| Genuine | Under a flake of the portrait's painted frame; square seal and II | 20 | OB | Second half of the written line |
| Decoy | Beneath the paint box; round potter's seal on a tally slip | 17 | 4321 | A stock count, not a square-sealed fragment |
| Decoy | In the empty incense brazier; oval seal on a charred strip | 20 | ASH | Plausible tomb language but the wrong seal |
| Decoy | Behind a replacement frame wedge; unsealed repair note | 17 | TI | No square seal or order numeral |

**Solution:** The square-sealed halves form **ENOB**. Reverse that entire
four-letter string to obtain **BONE**. Reversing each half separately without
reversing their order would incorrectly give NEBO.

**Failure and hints:** Wrong words make the coffer whisper the example,
"TAC becomes CAT," then reset the wheels. Repeated attempts are safe and free;
the painter's belongings and all clues remain intact.

**Reward:** The funerary coffer opens to reveal a carved ivory cameo and a
silver burial mask.

## Escape Rooms: Lookup Tables and Indexing

### 44. The Owl Librarian's Coordinates

**Escape code:** GATE

**Setup:** A deserted monastery library has a four-letter lock on its
forbidden archive. Most books carry catalogue numbers, but the old librarian
used a distinct owl seal for private instructions.

**Cipher key:** A brass grid beside the lock is visible and intact. Its
caption reads, "Follow the owl, I through IV. First number is ROW; second
number is COLUMN." The five-by-five alphabet omits J; no missing letter needs
to be guessed.

```text
    1 2 3 4 5
1   A B C D E
2   F G H I K
3   L M N O P
4   Q R S T U
5   V W X Y Z
```

**Search:** Roll basic + WIS modifier + applicable bonuses against the listed
DC. Each failed search costs an exploration turn and can be retried.
Inspecting the exact hiding place directly reveals its clue without a roll.

| Kind (TM only) | Hiding place and visible identifying marks | WIS DC | Found text | TM interpretation |
| --- | --- | --- | --- | --- |
| Genuine | Under the reading lectern's lip; owl seal and I | 17 | 22 | Row 2, column 2: G |
| Genuine | In a hollow book spine; owl seal and II | 20 | 11 | Row 1, column 1: A |
| Genuine | Behind the founder's portrait; owl seal and III | 20 | 44 | Row 4, column 4: T |
| Genuine | Inside the librarian's quill case; owl seal and IV | 17 | 15 | Row 1, column 5: E |
| Decoy | Under a shelf bracket; a serpent-stamped inventory label | 17 | 51 | Valid coordinates, wrong seal |
| Decoy | Between torn index pages; marked CATALOGUE, no owl | 17 | 43 | A shelf reference |
| Decoy | In a broken book clasp; a lion stamp | 20 | 25 | Valid coordinates belonging to another system |
| Decoy | Rolled inside a discarded reed pen; no seal | 20 | 3142 | A scribble without owl identification or an order numeral |

**Solution:** Read the owl-sealed coordinates in I-IV order: **22, 11, 44,
15**, producing **GATE**. Transposing the last pair to 51 gives V instead
of E; the grid's row-first instruction resolves that ambiguity.

**Failure and hints:** Incorrect words ring a small desk bell and reset
the lock. Attempts are unlimited. A miniature worked example on the grid
shows 12 selecting B, reinforcing row-then-column reading.

**Reward:** The archive door opens onto the protected section; a preserved
local map and an illuminated manuscript are displayed just beyond it.

### 45. The Smuggler's Waterlogged Testament

**Escape code:** MAP

**Setup:** A flooded storeroom contains a smuggler's skeleton, rotten cargo
tags, and a dry three-letter chest lock under a shelf. A waterproof notebook
has survived in a clearly visible glass-fronted niche.

**Cipher key:** The notebook's open page is fixed in place and reads:

```text
1 Beyond the mouth rest two lanterns
2 A rusted anchor guards the inlet
3 Stone pipes carry hidden cargo
```

Its margin explains, "Only swallowtail flags. Read I, II, III. A slash means
line/word; count words from one and take the first letter of the selected
word." Spaces separate words, and capitalization has no other meaning.

**Search:** Roll basic + WIS modifier + applicable bonuses against the listed
DC. A failed search spends an exploration turn; retries are allowed.
Direct inspection of the precise hiding place finds the clue without a roll.

| Kind (TM only) | Hiding place and visible identifying marks | WIS DC | Found text | TM interpretation |
| --- | --- | --- | --- | --- |
| Genuine | Stitched inside the skeleton's coat cuff; swallowtail flag and I | 20 | 1/3 | mouth: M |
| Genuine | Under the dry shelf's false bottom; swallowtail flag and II | 20 | 2/3 | anchor: A |
| Genuine | Inside a corked empty flask; swallowtail flag and III | 17 | 3/2 | pipes: P |
| Decoy | Beneath a barrel hoop; round warehouse stamp | 17 | 1/1 | A valid reference but not a swallowtail clue |
| Decoy | Behind a loose wall tile; square customs stamp | 20 | 3/1 | Another cargo system's reference |
| Decoy | In a split packing crate; unmarked price tag | 17 | 783 | No flag, numeral, or line/word separator |

**Solution:** Follow the flagged references in order. The chosen words are
**mouth, anchor, pipes**, whose first letters spell **MAP**. The notebook
is the complete lookup text; no book elsewhere in the dungeon is needed.

**Failure and hints:** Wrong words produce three hollow knocks. The chest
does not flood or consume clues, and entries may be retried indefinitely.
The margin's worked example says that 2/1 yields A.

**Reward:** The chest contains pearls wrapped in waxed cloth and a smuggler's
map identifying a useful dungeon shortcut.

## Escape Rooms: Binary and Signal Codes

### 46. The Surveyor's Three Warning Lamps

**Escape code:** 536

**Setup:** An abandoned mine survey station has a three-digit gate lock,
old lamp diagrams, and a collapsed survey tripod. Replacement parts lie
mixed with the original surveyor's marked copper plates.

**Cipher key:** A visible instruction board says, "Original copper plates
with triangular punch only; station order I, II, III." It assigns the three
lamp positions, left to right, weights **4, 2, 1**. A filled lamp, written
`1`, contributes its weight; an empty lamp, written `0`, contributes zero.
Add the lit weights to obtain each station's digit.

**Search:** Roll basic + WIS modifier + applicable bonuses against each
listed DC. Failure spends an exploration turn; repeat searches are allowed.
Exact inspection of a hiding place reveals its clue without another roll.

| Kind (TM only) | Hiding place and visible identifying marks | WIS DC | Found text | TM interpretation |
| --- | --- | --- | --- | --- |
| Genuine | Under the tripod's detachable foot; copper, triangular punch, I | 17 | 101 | 4 + 1 = 5 |
| Genuine | Beneath soot on a ceiling beam's mounted plate; copper, triangular punch, II | 20 | 011 | 2 + 1 = 3 |
| Genuine | Inside the surveyor's map tube; copper, triangular punch, III | 20 | 110 | 4 + 2 = 6 |
| Decoy | On the underside of a discarded lamp housing; brass replacement plate | 17 | 000 | Wrong material and no triangular punch |
| Decoy | Behind the coal bin; an unpunched charcoal tally on scrap wood | 17 | 111 | A shift tally, not an original plate |

**Solution:** In station order, the lamp groups contribute **5, 3, 6**.
Enter **536**. All lamps are drawn or inscribed symbols; the party does not
need working electrical equipment or fuel to decode them.

**Failure and hints:** Wrong entries make the instruction board briefly
illuminate the weights 4, 2, 1. The gate stays safely closed, the plates remain
readable, and there is no limit on retries.

**Reward:** The gate lifts to reveal the onward mine passage and a small
survey cache of polished crystals.

### 47. The Bellmaker's Interrupted Watch

**Escape code:** BELL

**Setup:** A clockwork workshop seals when its central bell is touched.
Four letter wheels appear on the release panel. The bellmaker's cracked
portrait overlooks piles of music sketches and abandoned signal records.

**Cipher key:** A visible signal chart supplies `B=-..., E=., L=.-..,
O=---, S=..., H=....`. Long marks are dashes; short marks are dots.
The panel says, "Only pendulum-sealed records; DAWN, NOON, DUSK, MIDNIGHT."
This is a supplied signal alphabet, not a test of players' knowledge of Morse.

**Search:** Roll basic + WIS modifier + applicable bonuses against the listed
DC. Misses cost an exploration turn and can be retried; directly examining
the actual hiding place reveals its clue without a roll.

| Kind (TM only) | Hiding place and visible identifying marks | WIS DC | Found text | TM interpretation |
| --- | --- | --- | --- | --- |
| Genuine | Behind the cracked portrait; pendulum seal and DAWN | 20 | -... | B |
| Genuine | Beneath the workbench vise's removable pad; pendulum seal and NOON | 17 | . | E |
| Genuine | Folded inside a stopped clock's openable case; pendulum seal and DUSK | 17 | .-.. | L |
| Genuine | Under a loose bell-mold insert; pendulum seal and MIDNIGHT | 20 | .-.. | L |
| Decoy | In the music-paper basket; a lyre stamp, no pendulum | 17 | --- | Decodes to O but fails the selection rule |
| Decoy | Inside a tuning-fork sleeve; marked PRACTICE with a round stamp | 20 | ... | Decodes to S but is not an official watch record |

**Solution:** Decode the four pendulum-sealed records in watch order to
obtain **BELL**, then enter it on the panel. Two different records correctly
give the same letter; duplicates are not evidence of a decoy.

**Failure and hints:** Wrong words make the bell tap the supplied example
for E. The room contains air and has no countdown; searches and code attempts
can be repeated. An interior emergency crank opens the way back after one
exploration turn of noisy work, but does not award the puzzle treasure or
bypass any separate progression gate.

**Reward:** The workshop releases its seals and opens a drawer containing
a silver handbell and a finely made set of clockmaker's tools.

## Escape Rooms: Ordering and Extraction

### 48. The Observatory's False Ephemerides

**Escape code:** SUN MOON STAR COMET

**Setup:** A ruined underground observatory has a passage lock with four
symbol rings. Each ring offers SUN, MOON, STAR, and COMET; a central mechanism
requires each symbol exactly once. Centuries of observation slips are scattered
around a broken viewing instrument.

**Cipher key:** A visible glossary reads `DAWN=SUN, TIDE=MOON, WATCHER=STAR,
WANDERER=COMET`. The lock's date plate says, "Current instructions: Year 417,
silver star seal." Old ephemerides and unsigned practice notes are not part
of the current code. The rings are read left to right.

**Search:** Roll basic + WIS modifier + applicable bonuses against each
listed DC. Failed attempts cost an exploration turn and may be repeated.
Direct inspection of the exact hiding place finds its clue without a roll.

| Kind (TM only) | Hiding place and visible identifying marks | WIS DC | Found text | TM interpretation |
| --- | --- | --- | --- | --- |
| Genuine | In the astronomer's boot lining; Year 417 and silver star seal | 17 | DAWN first | SUN occupies the leftmost ring |
| Genuine | Under the instrument's removable sight plate; Year 417 and silver star seal | 20 | WATCHER immediately after TIDE | STAR immediately follows MOON |
| Genuine | Behind a painting of the night sky; Year 417 and silver star seal | 20 | WANDERER last | COMET occupies the rightmost ring |
| Decoy | In a cracked scroll jar; silver star seal but Year 416 | 17 | WANDERER first | An obsolete instruction |
| Decoy | Beneath a stool; Year 417 but a crescent seal | 17 | WATCHER before DAWN | Wrong authority mark |
| Decoy | In the lens-cleaning rag box; unsealed scratch paper | 20 | TIDE WANDERER DAWN WATCHER | An unsigned trial ordering |

**Solution:** Translate the valid slips. SUN is first and COMET last; the
remaining two places must contain MOON immediately followed by STAR.
The unique code is **SUN MOON STAR COMET**. Both the date and seal matter
when filtering clues.

**Failure and hints:** A wrong arrangement projects the current Year 417
date and star seal, then releases the rings. Attempts are unlimited.
The mechanism rejects repeated symbols without treating that as a dangerous
mistake.

**Reward:** The passage iris opens, revealing onward access and a brass
star chart inlaid with small decorative gems.

### 49. The Field Surgeon's Linen Cipher

**Escape code:** HEAL

**Setup:** A deserted expedition infirmary contains a sealed four-letter
medicine chest, discarded treatment notes, and two empty field cots.
The surgeon hid the instructions among reusable bandages rather than in
the obvious paper records.

**Cipher key:** Two slotted frames are fixed beside the lock and labeled
`PULSE: 2,5` and `BREATH: 3,2`. A visible plaque says, "Use only sun-stitched
linen. Count letters from one, select in the printed order, and read PULSE
before BREATH." Holes in the frames demonstrate the same selections.

**Search:** Roll basic + WIS modifier + applicable bonuses against the listed
DC. A failed search costs an exploration turn; retries are permitted.
Inspecting the precise seam, pocket, or underside directly reveals its clue.

| Kind (TM only) | Hiding place and visible identifying marks | WIS DC | Found text | TM interpretation |
| --- | --- | --- | --- | --- |
| Genuine | Sewn into the first cot's mattress seam; sun-stitched linen labeled PULSE | 20 | SHARE | Letters 2 and 5 give HE |
| Genuine | Inside a clean bandage roll's core; sun-stitched linen labeled BREATH | 17 | FLASK | Letters 3 and 2 give AL |
| Decoy | In a bedside drawer's false bottom; paper labeled PULSE, no stitching | 20 | SCARS | The label fits, but the material and identifying mark do not |
| Decoy | Under an empty salve jar; paper labeled BREATH, no stitching | 17 | DRAKE | Not a sun-stitched linen strip |
| Decoy | Beneath the second cot; an unmarked inventory tally on wood | 17 | 1729 | A supply count unrelated to the letter frames |

**Solution:** Insert SHARE in the PULSE frame to select **H, E**; insert
FLASK in the BREATH frame to select **A, L** in that printed order.
Together they give **HEAL**. Do not rearrange the second frame's 3,2 into
ascending order.

**Failure and hints:** Incorrect words illuminate the frames' numbered
slots, then reset the lock. Attempts are unlimited. No chemicals, medicines,
or real wounds need to be tested to solve the cipher.

**Reward:** The chest contains a restorative potion and a silver surgical
instrument case.

### 50. The Cartographer's Serpent Trail

**Escape code:** SILVER

**Setup:** A collapsed surveying post has a hidden passage panel with six
letter wheels. A dead cartographer's map satchel and several generations of
route sketches lie beside a weathered relief of a serpent.

**Cipher key:** The serpent relief shows a two-column, three-row grid.
Its arrows read row I left to right, row II right to left, then row III
left to right. A caption says, "Only NORTH-UP fragments with the broken
mountain stamp. Fit I, II, III from top to bottom." Compass arrows are explicitly
labeled, and the broken and complete mountain stamps are visibly different.

**Search:** Roll basic + WIS modifier + applicable bonuses against the listed
DC. Each failure costs an exploration turn; retries are allowed.
Deliberately inspecting the exact hidden compartment or lining finds its clue
without another roll.

| Kind (TM only) | Hiding place and visible identifying marks | WIS DC | Found text | TM interpretation |
| --- | --- | --- | --- | --- |
| Genuine | Inside the map satchel's lining; NORTH-UP, broken mountain stamp, I | 20 | SI | Top row, read left to right |
| Genuine | Under the folding survey stool's seat; NORTH-UP, broken mountain stamp, II | 17 | VL | Middle row, read right to left |
| Genuine | Rolled into the hollow end of a measuring rod; NORTH-UP, broken mountain stamp, III | 20 | ER | Bottom row, read left to right |
| Decoy | Behind the satchel's buckle; NORTH-UP but a complete mountain stamp, III | 17 | ZZ | Wrong stamp |
| Decoy | In a discarded compass case; broken mountain stamp, II, but WEST-UP | 17 | TX | Wrong map orientation |
| Decoy | Beneath a loose paving stone; an unmarked merchant's price slip | 20 | YQ | No matching stamp, orientation, or row number |

**Solution:** Assemble rows **SI / VL / ER** and follow the serpent arrows:
SI, then LV, then ER. Enter **SILVER**. Ordinary left-to-right reading of
all rows would give SIVLER; the visible route explains the required transposition.

**Failure and hints:** Wrong words cause a harmless image of the serpent
to trace the three-row route, then reset the wheels. Retries are unlimited;
the fragments stay readable and need not be inserted into the lock itself.

**Reward:** The hidden survey passage opens and reveals a cache of silver
trade bars in the newly accessible section.
