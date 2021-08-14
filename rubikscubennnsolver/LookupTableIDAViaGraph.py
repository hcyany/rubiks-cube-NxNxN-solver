# standard libraries
import logging
import os
import subprocess
from typing import List

# rubiks cube libraries
from rubikscubennnsolver import reverse_steps
from rubikscubennnsolver.LookupTable import LookupTable, NoIDASolution, download_file_if_needed

logger = logging.getLogger(__name__)


def remove_failed_ida_output(lines: List[str]) -> List[str]:
    """
    Args:
        lines: log output from IDA

    Returns:
        the log output but with failed IDA output removed
    """
    result = []
    ida_output = []

    for line in lines:
        if line:
            ida_output.append(line)
        else:
            ida_output.append(line)

            if "IDA failed with range" not in "".join(ida_output):
                result.extend(ida_output)

            ida_output = []

    return result


class LookupTableIDAViaGraph(LookupTable):
    def __init__(
        self,
        parent,
        filename: str = None,
        all_moves: List[str] = [],
        illegal_moves: List[str] = [],
        state_target: str = None,
        linecount: int = None,
        max_depth: int = None,
        filesize: int = None,
        legal_moves: List[str] = [],
        prune_tables=[],
        multiplier: float = None,
        main_table_state_length: int = None,
        main_table_max_depth: int = None,
        main_table_prune_tables=None,
        perfect_hash01_filename: str = None,
        perfect_hash02_filename: str = None,
        pt1_state_max: int = None,
        pt2_state_max: int = None,
    ):
        LookupTable.__init__(self, parent, filename, state_target, linecount, max_depth, filesize)
        self.recolor_positions = []
        self.recolor_map = {}
        self.nuke_corners = False
        self.nuke_edges = False
        self.nuke_centers = False
        self.prune_tables = prune_tables
        self.multiplier = multiplier
        self.main_table_state_length = main_table_state_length
        self.main_table_max_depth = main_table_max_depth
        self.main_table_prune_tables = main_table_prune_tables

        if perfect_hash01_filename:
            self.perfect_hash01_filename = "lookup-tables/" + perfect_hash01_filename
        else:
            self.perfect_hash01_filename = perfect_hash01_filename

        if perfect_hash02_filename:
            self.perfect_hash02_filename = "lookup-tables/" + perfect_hash02_filename
        else:
            self.perfect_hash02_filename = perfect_hash02_filename

        self.pt1_state_max = pt1_state_max
        self.pt2_state_max = pt2_state_max

        if self.perfect_hash01_filename or self.pt1_state_max:
            assert (
                self.perfect_hash01_filename and self.pt1_state_max
            ), "both perfect_hash01_filename and pt1_state_max must be specified"
            download_file_if_needed(self.perfect_hash01_filename, self.parent.size)

        if self.perfect_hash02_filename or self.pt2_state_max:
            assert (
                self.perfect_hash02_filename and self.pt2_state_max
            ), "both perfect_hash02_filename and pt2_state_max must be specified"
            download_file_if_needed(self.perfect_hash02_filename, self.parent.size)

        if legal_moves:
            self.all_moves = list(legal_moves)
        else:
            for x in illegal_moves:
                if x not in all_moves:
                    raise Exception("illegal move %s is not in the list of legal moves" % x)

            self.all_moves = []

            for x in all_moves:
                if x not in illegal_moves:
                    self.all_moves.append(x)

        logger.debug("%s: all_moves %s" % (self, ",".join(self.all_moves)))
        COST_LENGTH = 1
        STATE_INDEX_LENGTH = 4
        self.ROW_LENGTH = COST_LENGTH + (STATE_INDEX_LENGTH * len(self.all_moves))

    def get_ida_graph_nodes(self):
        return [pt.ida_graph_node for pt in self.prune_tables]

    def set_ida_graph_nodes(self, ida_graph_nodes) -> None:
        for (pt, node) in zip(self.prune_tables, ida_graph_nodes):
            pt.ida_graph_node = node

    def init_state_index_caches(self) -> None:
        for pt in self.prune_tables:
            pt.load_state_index_cache()

    def init_ida_graph_nodes(self) -> None:
        for pt in self.prune_tables:
            pt.ida_graph_node = pt.state_index()

    def recolor(self):
        """
        re-color the cube per use_nuke_edges, etd and recolor_positions
        """

        if self.nuke_corners or self.nuke_edges or self.nuke_centers or self.recolor_positions:
            logger.info("%s: recolor" % self)
            # self.parent.print_cube()

            if self.nuke_corners:
                self.parent.nuke_corners()

            if self.nuke_edges:
                self.parent.nuke_edges()

            if self.nuke_centers:
                self.parent.nuke_centers()

            for x in self.recolor_positions:
                x_color = self.parent.state[x]
                x_new_color = self.recolor_map.get(x_color)

                if x_new_color:
                    self.parent.state[x] = x_new_color

            # self.parent.print_cube()
            # sys.exit(0)

    def build_ida_graph_set_cube_state(self, state, steps_to_scramble) -> None:
        # If the table we are building is one with multiple goal states then the
        # child class must override this method.
        self.parent.re_init()
        for step in steps_to_scramble:
            self.parent.rotate(step)

    def build_ida_graph(self, start=None, end=None):
        pt_state_filename = self.filename.replace(".txt", ".pt_state")

        if start is not None:
            pt_state_filename += f"-{start}-{end}"

        for pt in self.prune_tables:
            pt.load_ida_graph()

        to_write = []
        self.init_state_index_caches()

        with open(pt_state_filename, "w") as fh_pt_state:
            with open(self.filename, "r") as fh:
                for (line_number, line) in enumerate(fh):

                    if start is not None and line_number < start:
                        continue

                    if end is not None and line_number > end:
                        break

                    (state, steps_to_solve) = line.rstrip().split(":")
                    steps_to_solve = steps_to_solve.split()

                    if state in self.state_target:
                        cost_to_goal = 0
                    else:
                        cost_to_goal = len(steps_to_solve)

                    steps_to_scramble = reverse_steps(steps_to_solve)
                    self.build_ida_graph_set_cube_state(state, steps_to_scramble)
                    self.init_ida_graph_nodes()
                    pt_ida_graph_nodes = self.get_ida_graph_nodes()

                    lt_state = ""

                    for x in pt_ida_graph_nodes:
                        assert x <= 9999999
                        lt_state += f"{x:07d}-"

                    lt_state = lt_state.rstrip("-")
                    to_write.append(f"{lt_state}:{cost_to_goal}")

                    if line_number and line_number % 100000 == 0:
                        fh_pt_state.write("\n".join(to_write) + "\n")
                        to_write = []

                        if start is not None:
                            logger.info(f"{start:,}->{end:,} line {line_number:,}")
                        else:
                            logger.info(f"line {line_number:,}")

            if to_write:
                fh_pt_state.write("\n".join(to_write) + "\n")
                to_write = []

    def solve_via_c(self, pt_states=[], line_index_pre_steps={}, max_ida_threshold: int = None):
        cmd = ["./ida_search_via_graph"]
        my_pt_state_filename = "my-pt-states.txt"

        if pt_states:
            for (index, pt) in enumerate(self.prune_tables):
                cmd.append("--prune-table-%d-filename" % index)
                cmd.append(pt.filename.replace(".txt", ".bin"))

            with open(my_pt_state_filename, "w") as fh:
                for x in pt_states:
                    fh.write(",".join(map(str, x)) + "\n")
            cmd.append("--prune-table-states")
            cmd.append(my_pt_state_filename)
        else:
            self.init_ida_graph_nodes()

            for (index, pt) in enumerate(self.prune_tables):
                cmd.append("--prune-table-%d-filename" % index)
                cmd.append(pt.filename.replace(".txt", ".bin"))

                if not pt_states:
                    cmd.append("--prune-table-%d-state" % index)
                    cmd.append(str(pt.ida_graph_node))

        if self.avoid_oll is not None:
            orbits_with_oll = self.parent.center_solution_leads_to_oll_parity()

            if self.avoid_oll == 0 or self.avoid_oll == (0, 1):
                # Edge parity is currently odd so we need an odd number of w turns in orbit 0
                if 0 in orbits_with_oll:
                    cmd.append("--orbit0-need-odd-w")

                # Edge parity is currently even so we need an even number of w turns in orbit 0
                else:
                    cmd.append("--orbit0-need-even-w")

            if self.avoid_oll == 1 or self.avoid_oll == (0, 1):
                # Edge parity is currently odd so we need an odd number of w turns in orbit 1
                if 1 in orbits_with_oll:
                    cmd.append("--orbit1-need-odd-w")

                # Edge parity is currently even so we need an even number of w turns in orbit 1
                else:
                    cmd.append("--orbit1-need-even-w")

            if self.avoid_oll != 0 and self.avoid_oll != 1 and self.avoid_oll != (0, 1):
                raise Exception("avoid_oll is only supported for orbits 0 or 1, not {}".format(self.avoid_oll))

        if self.perfect_hash01_filename:
            cmd.append("--prune-table-perfect-hash01")
            cmd.append(self.perfect_hash01_filename)
            cmd.append("--pt1-state-max")
            cmd.append(str(self.pt1_state_max))

        if self.perfect_hash02_filename:
            cmd.append("--prune-table-perfect-hash02")
            cmd.append(self.perfect_hash02_filename)
            cmd.append("--pt2-state-max")
            cmd.append(str(self.pt2_state_max))

        if max_ida_threshold is not None:
            cmd.append("--max-ida-threshold")
            cmd.append(str(max_ida_threshold))

        cmd.append("--legal-moves")
        cmd.append(",".join(self.all_moves))

        # wrap the X,Y,Z part of "--legal-moves X,Y,Z" in double quotes
        cmd_string = " ".join(cmd)
        cmd_string = cmd_string.replace("--legal-moves ", '--legal-moves "')
        cmd_string += '"'

        if self.multiplier:
            cmd_string += f" --multiplier {self.multiplier}"
            cmd.append("--multiplier")
            cmd.append(str(self.multiplier))

        logger.info("solve_via_c:\n    %s\n" % cmd_string)

        output = subprocess.check_output(cmd).decode("utf-8").splitlines()
        last_solution = None
        last_solution_line_index = None

        if os.path.exists(my_pt_state_filename):
            os.unlink(my_pt_state_filename)

        for line in output:
            if line.startswith("SOLUTION:"):
                last_solution = line
            elif line.startswith("LINE INDEX"):
                last_solution_line_index = int(line.strip().split()[-1])

        if last_solution:
            self.parent.solve_via_c_output = "\n" + "\n".join(remove_failed_ida_output(output)) + "\n"
            logger.info(self.parent.solve_via_c_output)

            for step in line_index_pre_steps.get(last_solution_line_index, []):
                self.parent.rotate(step)

            solution = last_solution.strip().split(":")[1].split()
            for step in solution:
                self.parent.rotate(step)
            return last_solution_line_index

        raise NoIDASolution("Did not find SOLUTION line in\n%s\n" % "\n".join(output))
