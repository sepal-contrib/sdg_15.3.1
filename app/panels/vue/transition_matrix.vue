<template>
  <div>
    <div class="d-flex align-center">
      <span class="subtitle-2 font-weight-medium">{{ title }}</span>
      <v-spacer></v-spacer>
      <v-btn
        icon
        x-small
        :disabled="disabled || is_default"
        :title="reset_label"
        @click="resetToDefault"
      >
        <v-icon small>mdi-broom</v-icon>
      </v-btn>
    </div>

    <v-simple-table dense class="sdg-matrix" v-if="grid.length > 0">
      <template v-slot:default>
        <tbody>
          <tr>
            <th></th>
            <th v-for="(name, index) in class_names" :key="`head-${index}`" class="text-center">
              <v-tooltip bottom max-width="200">
                <template v-slot:activator="{ on, attrs }">
                  <span v-bind="attrs" v-on="on">{{ abbreviate(name) }}</span>
                </template>
                <span>{{ to_label }} {{ name }}</span>
              </v-tooltip>
            </th>
          </tr>

          <tr v-for="(row, rowIndex) in grid" :key="`row-${rowIndex}`">
            <th class="text-left">
              <v-tooltip bottom max-width="200">
                <template v-slot:activator="{ on, attrs }">
                  <span v-bind="attrs" v-on="on">{{ abbreviate(class_names[rowIndex]) }}</span>
                </template>
                <span>{{ from_label }} {{ class_names[rowIndex] }}</span>
              </v-tooltip>
            </th>

            <td
              v-for="(cell, colIndex) in row"
              :key="`cell-${rowIndex}-${colIndex}`"
              class="matrix-cell"
              :class="{ 'matrix-cell--live': !disabled }"
              :style="{ backgroundColor: cellColor(cell) }"
              :title="cellTooltip(rowIndex, colIndex, cell)"
              @click="cycle(rowIndex, colIndex, cell)"
            >
              {{ abbrev(cell) }}
            </td>
          </tr>
        </tbody>
      </template>
    </v-simple-table>
  </div>
</template>

<script>
/* Adapted from sepal_mgci's component/widget/vue/transitionMatrix.vue.
 *
 * Three deliberate departures, each a real defect in the original:
 *
 * 1. `module.exports`, not `modules.export`. MEASURED, not guessed: this
 *    template is evaluated by jupyter-vue's loader with `new Function`, which
 *    is not a module context. `modules.export` silently registers nothing, and
 *    `export default` -- the spelling nine pysepal components use, and the one
 *    tried first here -- is a hard `SyntaxError: Unexpected token 'export'`
 *    that leaves the widget blank. The console is the only place either shows.
 * 2. Cell values are compared with `== null`, never for truthiness. This
 *    matrix's vocabulary is -1 / 0 / +1 and zero is falsy in JS, so the
 *    original's ternary on the code blanks every Stable cell.
 * 3. The grid arrives as a grid, not rebuilt from a flat list of per-pair
 *    rows -- the shape the original's CSV happened to have, which costs a
 *    lookup per cell and silently drops any pair missing from the list.
 */
module.exports = {
  name: "TransitionMatrix",

  props: {
    class_names: { type: Array, default: () => [] },
    matrix: { type: Array, default: () => [] },
    default_matrix: { type: Array, default: () => [] },
    decode: { type: Object, default: () => ({}) },
    disabled: { type: Boolean, default: false },
    reset_label: { type: String, default: "" },
    from_label: { type: String, default: "" },
    to_label: { type: String, default: "" },
    cycle_label: { type: String, default: "" },
    title: { type: String, default: "" },
  },

  computed: {
    grid() {
      // A copy, never the `matrix` prop itself: writing through a prop is
      // something Vue forbids, and it would desynchronise the Python trait
      // that owns this value.
      return this.matrix.map((row) => row.slice());
    },

    /* The vocabulary, ascending: -1, 0, 1. `cycle` steps through it, so the
       order here is the order a repeated click walks. */
    values() {
      return Object.keys(this.decode)
        .map(Number)
        .sort((a, b) => a - b);
    },

    is_default() {
      return JSON.stringify(this.matrix) === JSON.stringify(this.default_matrix);
    },
  },

  methods: {
    option(value) {
      // String(value) because a Python dict keyed on ints reaches Vue with
      // string keys; `-1` and `0` both have to survive that.
      return value == null ? null : this.decode[String(value)] ?? null;
    },

    cellColor(value) {
      const option = this.option(value);
      return option && option.color ? option.color : "transparent";
    },

    abbrev(value) {
      const option = this.option(value);
      return option ? option.abrv : "";
    },

    cellTooltip(rowIndex, colIndex, value) {
      const option = this.option(value);
      const from = this.class_names[rowIndex];
      const to = this.class_names[colIndex];
      const label = option ? option.label : "";
      const hint = this.disabled ? "" : " — " + this.cycle_label;
      return from + " → " + to + ": " + label + hint;
    },

    /* One click advances to the next value. A dropdown per cell is the
       obvious control and was tried first: 49 `v-select` instances in a
       450px panel, and the menu never opened inside this template anyway.
       With three values a click reaches any of them in at most two, and the
       legend below the grid is what says which letter is which. */
    cycle(rowIndex, colIndex, value) {
      if (this.disabled) return;
      const order = this.values;
      const next = order[(order.indexOf(Number(value)) + 1) % order.length];
      this.onCellChange(rowIndex, colIndex, next);
    },

    abbreviate(name) {
      if (!name) return "";
      return name.length <= 12 ? name : `${name.slice(0, 10)}…`;
    },

    onCellChange(rowIndex, colIndex, value) {
      if (value == null) return;
      const next = this.matrix.map((row) => row.slice());
      next[rowIndex][colIndex] = Number(value);
      // Whole grid, not one cell: the Python side owns a frozen matrix, so
      // there is nothing to patch in place -- it rebuilds from what it gets.
      this.matrix = next;
    },

    resetToDefault() {
      this.matrix = this.default_matrix.map((row) => row.slice());
    },
  },
};
</script>

<style>
/* NOT `scoped`, and no `>>>` deep combinators: this template is compiled by
   jupyter-vue with `new Function`, not vue-loader, so neither the scoping
   attribute nor the deep selector is rewritten -- rules written that way
   never match anything. */
.sdg-matrix table {
  table-layout: fixed;
}

.sdg-matrix th,
.sdg-matrix td {
  padding: 2px !important;
  font-size: 11px;
  text-align: center;
  height: 26px !important;
}

.sdg-matrix th:first-child,
.sdg-matrix td:first-child {
  text-align: left;
}

.matrix-cell--live {
  cursor: pointer;
  user-select: none;
}

.matrix-cell--live:hover {
  outline: 1px solid currentColor;
  outline-offset: -1px;
}
</style>
